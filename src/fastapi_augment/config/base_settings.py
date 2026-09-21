"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 基于 pydantic-settings 的通用配置管理
                  - 支持从环境变量、.env、JSON、YAML、TOML 多种来源加载
                  - 支持环境变量前缀与嵌套配置（通过分隔符）
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic_settings import (
    PydanticBaseSettingsSource,
    JsonConfigSettingsSource,
    YamlConfigSettingsSource,
    TomlConfigSettingsSource,
    BaseSettings,
    SettingsConfigDict
)

# SettingsConfigDict 所有可用键，用于区分配置参数和模型字段值
_CONFIG_KEYS = frozenset(SettingsConfigDict.__annotations__.keys())

# 文件型配置键 → 对应的 SettingsSource 类
_FILE_SOURCE_MAP: dict[str, type[PydanticBaseSettingsSource]] = {
    'json_file': JsonConfigSettingsSource,
    'yaml_file': YamlConfigSettingsSource,
    'toml_file': TomlConfigSettingsSource,
}

# 动态子类缓存：按 (原类, config_overrides) 复用子类，避免重复 type() 累积类对象
_SUBCLASS_CACHE: dict[tuple[type, frozenset[tuple[str, Any]]], type] = {}


class AugmentBaseSettings(BaseSettings):
    """应用配置基类，继承 pydantic_settings.BaseSettings

    支持多种配置来源，通过不同类方法加载::

        from fastapi_augment.config import AugmentBaseSettings

        class Settings(AugmentBaseSettings):
            database_url: str
            redis_url: str = ''
            debug: bool = False

        # 从环境变量加载
        cfg = Settings.from_env(env_prefix='APP_')

        # 从 .env 文件加载
        cfg = Settings.from_dotenv('.env', env_prefix='APP_')

        # 从 JSON 文件加载
        cfg = Settings.from_json('config.json')

        # 从 YAML 文件加载
        cfg = Settings.from_yaml('config.yaml')

        # 从 TOML 文件加载
        cfg = Settings.from_toml('config.toml')

    特性：
        - 支持多种配置来源：环境变量、.env、JSON、YAML、TOML
        - 支持 ``env_prefix`` 前缀过滤（如 ``APP_`` → ``APP_DATABASE_URL``）
        - 支持 ``env_nested_delimiter`` 嵌套配置（如 ``DB__URL=xxx``）
        - 环境变量优先级高于配置文件
        - 默认 ``extra='ignore'``，未声明的配置项被安全忽略
    """

    model_config = SettingsConfigDict(
        env_prefix='',
        env_file=None,
        env_nested_delimiter=None,
        case_sensitive=False,
        extra='ignore',
    )

    # ------------------------------
    # 内部构建
    # ------------------------------
    @classmethod
    def _build(cls, config_kwargs: dict[str, Any], field_overrides: dict[str, Any]) -> AugmentBaseSettings:
        """根据配置参数和字段覆盖构建配置实例

        自动区分 ``SettingsConfigDict`` 参数和模型字段值：
        - 属于 ``SettingsConfigDict`` 的键 → 覆盖 ``model_config``
        - 其余键 → 直接覆盖模型字段值

        当包含 JSON/YAML/TOML 文件配置时，自动注入 ``settings_customise_sources``
        以注册对应的文件配置源

        Args:
            config_kwargs: 预设的配置参数（如 env_file、json_file 等）
            field_overrides: 模型字段覆盖和其他 kwargs

        Returns:
            配置实例
        """
        config_overrides: dict[str, Any] = {}
        fields: dict[str, Any] = {}

        for key, value in {**config_kwargs, **field_overrides}.items():
            if key in _CONFIG_KEYS:
                config_overrides[key] = str(value) if key == 'env_file' and value is not None else value
            else:
                fields[key] = value

        if config_overrides:
            # 检测是否需要注入文件型配置源
            file_source_keys = [k for k in _FILE_SOURCE_MAP if k in config_overrides]
            class_attrs: dict[str, Any] = {
                'model_config': SettingsConfigDict(**{**dict(cls.model_config), **config_overrides}),
            }

            if file_source_keys:
                class_attrs['settings_customise_sources'] = staticmethod(
                    cls._make_customise_sources(file_source_keys)
                )

            # 按 (原类, 配置覆盖) 缓存动态子类，避免重复创建累积类对象
            cache_key = (cls, frozenset(config_overrides.items()))
            sub_cls = _SUBCLASS_CACHE.get(cache_key)
            if sub_cls is None:
                sub_cls = type(f'{cls.__name__}__env', (cls,), class_attrs)
                _SUBCLASS_CACHE[cache_key] = sub_cls
            return sub_cls(**fields)  # type: ignore[arg-type]

        return cls(**fields)  # type: ignore[arg-type]

    # ------------------------------
    # 工厂方法
    # ------------------------------
    @classmethod
    def from_env(cls, **kwargs: Any) -> AugmentBaseSettings:
        """从环境变量加载配置，支持 ``SettingsConfigDict`` 所有参数

        内部自动区分 ``SettingsConfigDict`` 配置参数和模型字段值：
        - 属于 ``SettingsConfigDict`` 的键 → 覆盖 ``model_config``
        - 其余键 → 直接覆盖模型字段值（优先级最高）

        常用配置参数：
            env_prefix: 环境变量前缀（如 ``'APP_'``）
            env_nested_delimiter: 嵌套配置分隔符（如 ``'__'``）
            case_sensitive: 环境变量大小写敏感
            secrets_dir: secrets 目录路径
            cli_parse_args: 是否解析命令行参数

        Args:
            **kwargs: ``SettingsConfigDict`` 参数和模型字段值混合传入

        Returns:
            配置实例

        Example::

            cfg = Settings.from_env(
                env_prefix='APP_',
                env_nested_delimiter='__',
                debug=True,               # 模型字段值覆盖
            )
        """
        return cls._build({}, kwargs)

    @classmethod
    def from_dotenv(cls, env_file: str | Path, **kwargs: Any) -> AugmentBaseSettings:
        """从 ``.env`` 文件加载配置

        环境变量优先级高于 .env 文件中的值

        Args:
            env_file: .env 文件路径
            **kwargs: ``SettingsConfigDict`` 参数和模型字段值

        Returns:
            配置实例

        Example::

            cfg = Settings.from_dotenv('.env', env_prefix='APP_')
        """
        return cls._build({'env_file': env_file}, kwargs)

    @classmethod
    def from_json(cls, json_file: str | Path, **kwargs: Any) -> AugmentBaseSettings:
        """从 JSON 文件加载配置

        Args:
            json_file: JSON 配置文件路径
            **kwargs: ``SettingsConfigDict`` 参数（如 ``json_file_encoding``）和模型字段值

        Returns:
            配置实例

        Example::

            cfg = Settings.from_json('config.json')
        """
        return cls._build({'json_file': json_file}, kwargs)

    @classmethod
    def from_yaml(cls, yaml_file: str | Path, **kwargs: Any) -> AugmentBaseSettings:
        """从 YAML 文件加载配置

        Args:
            yaml_file: YAML 配置文件路径
            **kwargs: ``SettingsConfigDict`` 参数（如 ``yaml_file_encoding``、
                ``yaml_config_section``）和模型字段值

        Returns:
            配置实例

        Example::

            cfg = Settings.from_yaml('config.yaml')
        """
        return cls._build({'yaml_file': yaml_file}, kwargs)

    @classmethod
    def from_toml(cls, toml_file: str | Path, **kwargs: Any) -> AugmentBaseSettings:
        """从 TOML 文件加载配置

        Args:
            toml_file: TOML 配置文件路径
            **kwargs: ``SettingsConfigDict`` 参数（如 ``toml_table_header``）和模型字段值

        Returns:
            配置实例

        Example::

            cfg = Settings.from_toml('config.toml')
        """
        return cls._build({'toml_file': toml_file}, kwargs)

    @staticmethod
    def _make_customise_sources(file_source_keys: list[str]) -> Callable:
        """为动态子类生成 ``settings_customise_sources`` 函数

        根据所需的文件配置键，选择对应的 Source 类并注入到 sources 列表中

        Args:
            file_source_keys: 需要注入的文件配置键列表（如 ``['json_file']``）

        Returns:
            用于绑定为 staticmethod 的函数
        """
        sources_to_add = [_FILE_SOURCE_MAP[key] for key in file_source_keys]

        def _customise(
                cls: type[AugmentBaseSettings],
                init_settings: PydanticBaseSettingsSource,
                env_settings: PydanticBaseSettingsSource,
                dotenv_settings: PydanticBaseSettingsSource,
                file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            file_sources = tuple(src_cls(cls) for src_cls in sources_to_add)  # type: ignore[arg-type]
            # 优先级：init > env > dotenv > 文件配置 > secrets
            return (init_settings, env_settings, dotenv_settings, *file_sources, file_secret_settings)  # type: ignore[return-value]

        return _customise
