"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : Uvicorn 运行参数配置——字段通过 QUICKSTART_UVICORN_ 前缀覆盖；不使用 uvicorn 时无需定义
"""
from fastapi_augment.config import AugmentBaseSettings

from .project_settings import project_settings
from .settings import root_dir, ENV_PREFIX


class UvicornSettings(AugmentBaseSettings):
    """Uvicorn 运行配置，字段通过 QUICKSTART_UVICORN_ 前缀的环境变量或 .env 覆盖

    Example:
        .env 中写 ``QUICKSTART_UVICORN_PORT=9000`` 即可将端口改为 9000
    """
    host: str = '0.0.0.0'
    port: int = 8000
    workers: int = 2
    access_log: bool = True
    root_path: str = ''
    asgi_app_ref: str = 'apps.api:app'  # 启动入口，可用环境变量覆盖

    @property
    def reload(self) -> bool:
        """是否开启热重载

        联动项目 debug 开关：调试模式下自动 reload，生产环境关闭。

        Returns:
            是否开启热重载
        """
        return project_settings.debug


# 配置实例
uvicorn_settings = UvicornSettings.from_env(
    env_file=root_dir / '.env',
    env_prefix=f'{ENV_PREFIX}UVICORN_',
    env_nested_delimiter='__',
    env_parse_none_str='null'
)
