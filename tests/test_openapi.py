"""
openapi 模块测试 — OpenAPICustomConfig / configure_openapi_schema
"""
from fastapi import FastAPI

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
