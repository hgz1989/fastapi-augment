"""
@Author         : hangu
@CreateDate     : 2026/9/30
@Description    : 包资源读取——docs 登录页 / ReDoc 的 logo 等静态资源

    资源文件统一放在 ``fastapi_augment/assets/`` 目录（随包分发）。
    浏览器无法直接访问库安装目录的相对路径，因此这里把资源读取后
    转为 ``data:`` URI 内联到 HTML / OpenAPI schema 中，无需静态挂载。

    Example::

        # 默认 logo（assets/logo.png 存在时返回 data URI，否则 None）
        logo = package_asset_data_uri('logo.png')
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

# 包内资源根目录：fastapi_augment/assets
# resources.py 位于 fastapi_augment/common/utils/，parents[2] 即 fastapi_augment
ASSETS_DIR: Path = Path(__file__).resolve().parents[2] / 'assets'


def file_data_uri(path: str | Path) -> str | None:
    """将本地文件读取为 ``data:`` URI；文件不存在或读取失败时返回 None

    Args:
        path: 本地文件路径

    Returns:
        data URI 字符串（如 ``data:image/png;base64,xxxx``）；文件缺失返回 None
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None

    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = 'application/octet-stream'
    encoded = base64.b64encode(raw).decode('ascii')
    return f'data:{mime};base64,{encoded}'


def package_asset_data_uri(
        name: str,
        assets_dir: Path = ASSETS_DIR,
) -> str | None:
    """将包内资源文件读取为 ``data:`` URI，文件不存在或读取失败时返回 None

    Args:
        name: 资源文件名（相对 assets 目录），如 ``logo.png``
        assets_dir: 资源根目录，默认 ``fastapi_augment/assets``

    Returns:
        data URI 字符串；资源缺失返回 None
    """
    return file_data_uri(assets_dir / name)
