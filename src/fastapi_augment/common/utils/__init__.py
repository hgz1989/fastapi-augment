"""
@Author         : hangu
@CreateDate     : 2026/9/4
@Description    : 通用工具函数（路径、字符串、JSON 序列化）
"""
from .paths import find_project_root, get_root_dir
from .strings import (
    SupportsWriteStr,
    SupportsReadBytes,
    camel_to_snake,
    snake_to_camel,
    random_string,
    json_dumps,
    json_dump,
    json_loads,
    json_load
)

__all__ = [
    # paths
    'find_project_root',
    'get_root_dir',
    # strings
    'SupportsWriteStr',
    'SupportsReadBytes',
    'camel_to_snake',
    'snake_to_camel',
    'random_string',
    'json_dumps',
    'json_dump',
    'json_loads',
    'json_load'
]
