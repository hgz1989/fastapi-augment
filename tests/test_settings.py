"""
config.base_settings 模块测试 — AugmentBaseSettings.from_env() / from_dotenv() / from_json() 配置管理
"""
import pytest

from fastapi_augment.config.base_settings import (
    AugmentBaseSettings
)


# ── 测试用配置类 ──────────────────────────────────────────────────────

class Settings(AugmentBaseSettings):
    database_url: str = 'sqlite:///default.db'
    debug: bool = False
    secret_key: str = 'change-me'


# ── Tests ─────────────────────────────────────────────────────────────

class TestAugmentBaseSettings:

    def test_default_values(self):
        cfg = Settings()
        assert cfg.database_url == 'sqlite:///default.db'
        assert cfg.debug is False
        assert cfg.secret_key == 'change-me'

    def test_from_env_field_overrides(self):
        cfg = Settings.from_env(debug=True, secret_key='my-secret')
        assert cfg.debug is True
        assert cfg.secret_key == 'my-secret'
        # 未覆盖的字段保持默认
        assert cfg.database_url == 'sqlite:///default.db'

    def test_from_env_extra_ignore(self):
        """extra='ignore' — 未声明的字段被安全忽略"""
        cfg = Settings.from_env(nonexistent_field='ignored')
        assert cfg.database_url == 'sqlite:///default.db'

    def test_from_env_with_env_prefix(self, monkeypatch: pytest.MonkeyPatch):
        """env_prefix 过滤环境变量"""
        monkeypatch.setenv('MYAPP_DATABASE_URL', 'postgresql://prod/db')
        monkeypatch.setenv('MYAPP_DEBUG', 'true')

        cfg = Settings.from_env(env_prefix='MYAPP_')
        assert cfg.database_url == 'postgresql://prod/db'
        assert cfg.debug is True

    def test_from_env_config_vs_field_separation(self):
        """SettingsConfigDict 参数和模型字段值被正确区分"""
        cfg = Settings.from_env(
            env_prefix='TEST_',       # → SettingsConfigDict
            debug=True,               # → 模型字段值
        )
        assert cfg.debug is True
        # model_config 被覆盖为带前缀
        assert cfg.model_config.get('env_prefix') == 'TEST_'

    def test_from_env_returns_correct_type(self):
        cfg = Settings.from_env(debug=True)
        assert isinstance(cfg, Settings)

    def test_from_env_subclass_cached(self):
        """相同配置参数复用缓存的动态子类，不同参数创建不同子类"""
        cls1 = type(Settings.from_env(env_prefix='P1_'))
        cls2 = type(Settings.from_env(env_prefix='P1_'))
        cls3 = type(Settings.from_env(env_prefix='P2_'))
        assert cls1 is cls2
        assert cls1 is not cls3

    def test_env_override_beats_default(self, monkeypatch: pytest.MonkeyPatch):
        """环境变量优先级高于默认值"""
        monkeypatch.setenv('DATABASE_URL', 'postgresql://env/db')
        cfg = Settings()
        assert cfg.database_url == 'postgresql://env/db'


class TestAugmentBaseSettingsWithDotenv:

    def test_from_dotenv_with_env_file(self, tmp_path):
        """from_dotenv 加载 .env 文件"""
        env_file = tmp_path / '.env'
        env_file.write_text('DATABASE_URL=sqlite:///from_file.db\nDEBUG=true\n')

        cfg = Settings.from_dotenv(str(env_file))
        assert cfg.database_url == 'sqlite:///from_file.db'
        assert cfg.debug is True

    def test_from_dotenv_with_prefix(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        """from_dotenv 支持额外 SettingsConfigDict 参数"""
        env_file = tmp_path / '.env'
        env_file.write_text('APP_DEBUG=true\n')

        cfg = Settings.from_dotenv(str(env_file), env_prefix='APP_')
        assert cfg.debug is True


class TestAugmentBaseSettingsWithJson:

    def test_from_json(self, tmp_path):
        """from_json 加载 JSON 配置文件"""
        import json
        json_file = tmp_path / 'config.json'
        json_file.write_text(json.dumps({
            'database_url': 'sqlite:///from_json.db',
            'debug': True
        }))

        cfg = Settings.from_json(str(json_file))
        assert cfg.database_url == 'sqlite:///from_json.db'
        assert cfg.debug is True


class TestAugmentBaseSettingsWithYaml:

    def test_from_yaml(self, tmp_path):
        """from_yaml 加载 YAML 配置文件"""
        yaml_file = tmp_path / 'config.yaml'
        yaml_file.write_text('database_url: sqlite:///from_yaml.db\ndebug: true\n')

        cfg = Settings.from_yaml(str(yaml_file))
        assert cfg.database_url == 'sqlite:///from_yaml.db'
        assert cfg.debug is True


class TestAugmentBaseSettingsWithToml:

    def test_from_toml(self, tmp_path):
        """from_toml 加载 TOML 配置文件"""
        toml_file = tmp_path / 'config.toml'
        toml_file.write_text(
            'database_url = "sqlite:///from_toml.db"\n'
            'debug = true\n'
        )

        cfg = Settings.from_toml(str(toml_file))
        assert cfg.database_url == 'sqlite:///from_toml.db'
        assert cfg.debug is True
