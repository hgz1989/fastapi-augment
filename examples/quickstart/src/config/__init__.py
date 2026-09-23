"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 配置模块统一出口——三段式配置（全局 / 项目 / Uvicorn）
"""
from .project_settings import ProjectSettings, project_settings
from .settings import (
    Settings,
    settings,
    VERSION,
    ENV_PREFIX,
    root_dir,
)
from .uvicorn_settings import UvicornSettings, uvicorn_settings

# 模块顶层运行时版本引用；真正给 hatchling 解析的字面量在 settings.py 的 VERSION（见 pyproject [tool.hatch.version]）
__version__ = VERSION

__all__ = [
    'ProjectSettings',
    'project_settings',
    'Settings',
    'settings',
    'UvicornSettings',
    'uvicorn_settings',
    'VERSION',
    'ENV_PREFIX',
    'root_dir',
]
