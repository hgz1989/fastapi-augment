"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 项目元信息配置——debug / title / summary / version，字段通过 QUICKSTART_PROJECT_ 前缀覆盖
"""
from fastapi_augment.config import AugmentBaseSettings

from .settings import VERSION, root_dir, ENV_PREFIX


class ProjectSettings(AugmentBaseSettings):
    """项目基础配置，字段通过 QUICKSTART_PROJECT_ 前缀的环境变量或 .env 覆盖

    Example:
        .env 中写 ``QUICKSTART_PROJECT_DEBUG=true`` 即可开启调试模式
    """
    debug: bool = False
    title: str = 'fastapi-augment-quickstart'
    summary: str = 'fastapi-augment 完整可跑示例项目——展示核心能力与推荐工程模式'

    @property
    def version(self) -> str:
        """项目版本号

        Returns:
            项目版本号（唯一版本源，取自 settings.VERSION）
        """
        return VERSION


# 配置实例
project_settings = ProjectSettings.from_env(
    env_file=root_dir / '.env',
    env_prefix=f'{ENV_PREFIX}PROJECT_',
    env_nested_delimiter='__',
    env_parse_none_str='null'
)
