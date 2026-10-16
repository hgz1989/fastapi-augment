"""
openapi 模块测试 — OpenAPICustomConfig / configure_openapi_schema
"""
from fastapi import APIRouter, FastAPI

from fastapi_augment.openapi import (
    OpenAPICustomConfig,
    configure_openapi_schema
)


def _make_app_with_route(config: OpenAPICustomConfig | None = None) -> FastAPI:
    """创建带一个简单路由的 FastAPI 应用并配置 OpenAPI"""
    app = FastAPI(title='TestApp', version='1.0.0')

    @app.get('/hello')
    async def hello(name: str = 'world'):
        return {'message': f'hello {name}'}

    configure_openapi_schema(app, config=config)
    return app


def _make_app_with_callback(config: OpenAPICustomConfig | None = None) -> FastAPI:
    """创建带 OpenAPI callback 声明的应用并配置 OpenAPI"""
    callback_router = APIRouter()

    @callback_router.post('/callback/{item_id}')
    async def notify_callback(item_id: int, q: str = 'x'):
        pass

    app = FastAPI(title='TestApp', version='1.0.0')

    @app.post('/items', callbacks=callback_router.routes)
    async def create_item(name: str):
        return {'name': name}

    configure_openapi_schema(app, config=config)
    return app


# ── OpenAPICustomConfig ───────────────────────────────────────────────

class TestOpenAPICustomConfig:

    def test_default_values(self):
        cfg = OpenAPICustomConfig()
        assert cfg.remove_422 is True
        assert cfg.remove_validation_error_schema is True

    def test_custom_values(self):
        cfg = OpenAPICustomConfig(
            remove_422=False,
            remove_validation_error_schema=False,
        )
        assert cfg.remove_422 is False
        assert cfg.remove_validation_error_schema is False


# ── configure_openapi_schema ──────────────────────────────────────────

class TestConfigureOpenapiSchema:

    def test_remove_422_responses(self):
        app = _make_app_with_route(OpenAPICustomConfig(remove_422=True))
        schema = app.openapi()
        assert schema is not None
        for path_item in schema['paths'].values():
            for method_obj in path_item.values():
                if isinstance(method_obj, dict):
                    assert '422' not in method_obj.get('responses', {})

    def test_keep_422_responses(self):
        app = _make_app_with_route(OpenAPICustomConfig(remove_422=False))
        schema = app.openapi()
        assert schema is not None
        # /hello 有 query 参数，应产生 422 响应
        hello_get = schema['paths']['/hello']['get']
        assert '422' in hello_get['responses']

    def test_remove_422_responses_in_callbacks(self):
        """callback 声明内嵌操作的 422 响应一并移除"""
        app = _make_app_with_callback(OpenAPICustomConfig(remove_422=True))
        schema = app.openapi()
        assert schema is not None
        callbacks = schema['paths']['/items']['post']['callbacks']
        # 主操作与全部内嵌回调操作均不应残留 422
        assert '422' not in schema['paths']['/items']['post']['responses']
        for callback_paths in callbacks.values():
            for path_item in callback_paths.values():
                for method_obj in path_item.values():
                    assert '422' not in method_obj['responses']

    def test_keep_422_responses_in_callbacks(self):
        """remove_422=False 时 callback 内嵌操作保留 422 响应"""
        app = _make_app_with_callback(OpenAPICustomConfig(remove_422=False))
        schema = app.openapi()
        assert schema is not None
        callbacks = schema['paths']['/items']['post']['callbacks']
        callback_422 = [
            '422'
            for callback_paths in callbacks.values()
            for path_item in callback_paths.values()
            for method_obj in path_item.values()
            if '422' in method_obj['responses']
        ]
        assert callback_422, '回调操作带参数，应产生 422 响应'

    def test_remove_validation_error_schema(self):
        app = _make_app_with_route(OpenAPICustomConfig(
            remove_validation_error_schema=True,
            remove_422=False,
        ))
        schema = app.openapi()
        assert schema is not None
        schemas = schema.get('components', {}).get('schemas', {})
        assert 'ValidationError' not in schemas
        assert 'HTTPValidationError' not in schemas

    def test_schema_cached(self):
        app = _make_app_with_route()
        schema1 = app.openapi()
        schema2 = app.openapi()
        assert schema1 is schema2

    def test_openapi_disabled_returns_none(self):
        app = FastAPI(title='Test', openapi_url=None)

        @app.get('/test')
        async def test_ep():
            return {}

        configure_openapi_schema(app)
        assert app.openapi() is None

    def test_default_config_when_none(self):
        """传入 config=None 使用默认配置"""
        app = FastAPI(title='Test')

        @app.get('/test')
        async def test_ep():
            return {}

        configure_openapi_schema(app, config=None)
        schema = app.openapi()
        assert schema is not None
        assert schema['info']['title'] == 'Test'

    def test_logo_injects_x_logo(self):
        """配置 logo 时注入 OpenAPI info.x-logo（ReDoc 读取）"""
        app = _make_app_with_route(OpenAPICustomConfig(
            logo='data:image/png;base64,AAAA',
            logo_alt_text='My Logo',
        ))
        schema = app.openapi()
        assert schema is not None
        x_logo = schema['info']['x-logo']
        assert x_logo['url'] == 'data:image/png;base64,AAAA'
        assert x_logo['altText'] == 'My Logo'

    def test_no_logo_no_x_logo(self):
        """未配置 logo 时不注入 x-logo"""
        app = _make_app_with_route(OpenAPICustomConfig())
        schema = app.openapi()
        assert schema is not None
        assert 'x-logo' not in schema['info']
