"""
@Author         : hangu
@CreateDate     : 2026/8/31
@Description    : fastapi-augment — FastAPI 通用代码工具包，跨项目复用
"""
from .factory import create_app
from .lifespan import (
    HookFunc,
    HookRegistry,
    core_registry,
    fastapi_lifespan,
    clear_hooks
)
from .settings import AugmentBaseSettings

__all__ = [
    # factory
    'create_app',
    # lifespan
    'HookFunc',
    'HookRegistry',
    'core_registry',
    'fastapi_lifespan',
    'clear_hooks',
    'AugmentBaseSettings'
]
