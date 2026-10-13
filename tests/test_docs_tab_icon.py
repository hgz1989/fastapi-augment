"""
docs_logo 复用为 /docs 与 /redoc 标签页图标（favicon）测试

create_app 会把解析出的 logo（含包内默认 assets/logo.png）写入 FastAPI
内置页面函数的 __kwdefaults__ 默认参数（进程级），本模块用例快照并恢复
该全局状态，避免污染其他测试
"""
import pytest
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html
)
from starlette.testclient import TestClient

from fastapi_augment.factory import create_app


def _swagger_favicon() -> str:
    """内置 Swagger 页面函数当前的 favicon 默认值"""
    defaults = get_swagger_ui_html.__kwdefaults__
    assert defaults is not None
    return defaults['swagger_favicon_url']


def _redoc_favicon() -> str:
    """内置 ReDoc 页面函数当前的 favicon 默认值"""
    defaults = get_redoc_html.__kwdefaults__
    assert defaults is not None
    return defaults['redoc_favicon_url']


@pytest.fixture(autouse=True)
def _restore_page_defaults():
    """快照并恢复内置页面函数 __kwdefaults__（用例会改写进程级默认参数）"""
    swagger_defaults = dict(get_swagger_ui_html.__kwdefaults__ or {})
    redoc_defaults = dict(get_redoc_html.__kwdefaults__ or {})
    yield
    swagger_current = get_swagger_ui_html.__kwdefaults__
    if swagger_current is not None:
        swagger_current.clear()
        swagger_current.update(swagger_defaults)
    redoc_current = get_redoc_html.__kwdefaults__
    if redoc_current is not None:
        redoc_current.clear()
        redoc_current.update(redoc_defaults)


# ── 标签页图标复用 logo ──────────────────────────────────────────────

class TestDocsTabIcon:

    def test_url_logo_used_as_both_favicons(self):
        """docs_logo 传 URL 时 /docs 与 /redoc 标签页图标均为该 URL"""
        create_app(docs_logo='https://example.com/logo.png')
        assert _swagger_favicon() == 'https://example.com/logo.png'
        assert _redoc_favicon() == 'https://example.com/logo.png'

    def test_local_path_logo_as_data_uri(self, tmp_path):
        """docs_logo 传本地路径时标签页图标转为 data URI（两页一致）"""
        logo_file = tmp_path / 'logo.png'
        logo_file.write_bytes(b'\x89PNG\x0d\x0a\x1a\x0a')
        create_app(docs_logo=logo_file)
        favicon = _swagger_favicon()
        assert favicon.startswith('data:image/png;base64,')
        assert _redoc_favicon() == favicon

    def test_package_default_logo_reused(self):
        """未传 docs_logo 时包内默认 logo.png 的解析结果同样复用到标签页图标"""
        from fastapi_augment.common.utils.resources import package_asset_data_uri

        expected = package_asset_data_uri('logo.png')
        assert expected is not None  # 库内随包分发 assets/logo.png
        create_app()
        assert _swagger_favicon() == expected
        assert _redoc_favicon() == expected

    def test_no_logo_keeps_current_favicon(self, monkeypatch):
        """无可用 logo（未显式传入且包内默认缺失）时保持原标签页图标"""
        monkeypatch.setattr(
            'fastapi_augment.factory.package_asset_data_uri',
            lambda *args, **kwargs: None,
        )
        before_swagger = _swagger_favicon()
        before_redoc = _redoc_favicon()
        create_app()
        assert _swagger_favicon() == before_swagger
        assert _redoc_favicon() == before_redoc

    def test_docs_page_renders_logo_favicon(self):
        """GET /docs 页面 HTML 的 favicon 引用为配置的 logo"""
        app = create_app(docs_logo='https://example.com/logo.png')
        page = TestClient(app).get('/docs').text
        assert 'rel="shortcut icon"' in page
        assert 'https://example.com/logo.png' in page

    def test_redoc_page_renders_logo_favicon(self):
        """GET /redoc 页面 HTML 的 favicon 引用为配置的 logo"""
        app = create_app(docs_logo='https://example.com/logo.png')
        page = TestClient(app).get('/redoc').text
        assert 'rel="shortcut icon"' in page
        assert 'https://example.com/logo.png' in page
