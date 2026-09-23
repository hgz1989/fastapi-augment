"""
factory 模块测试 — create_app 应用工厂
"""
import pytest
from fastapi import FastAPI, APIRouter
from starlette.testclient import TestClient

from fastapi_augment.factory import (
    create_app,
    _resolve_registries
)
from fastapi_augment.lifespan import HookRegistry


# ── 基础创建 ──────────────────────────────────────────────────────────

class TestCreateAppBasic:

    def test_returns_fastapi_instance(self):
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_default_metadata(self):
        app = create_app()
        assert app.title == 'FastAPI Augment'
        assert app.version == '0.1.6'
        assert app.description.startswith('FastAPI Augment')

    def test_custom_metadata(self):
        app = create_app(title='MyApp', version='2.0.0', description='test desc')
        assert app.title == 'MyApp'
        assert app.version == '2.0.0'
        assert app.description == 'test desc'

    def test_debug_mode(self):
        app = create_app(debug=True)
        assert app.debug is True

    def test_disable_docs(self):
        app = create_app(docs_url=None, redoc_url=None, openapi_url=None)
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None


# ── lifespan 校验 ─────────────────────────────────────────────────────

class TestCreateAppLifespan:

    def test_reject_lifespan_in_kwargs(self):
        with pytest.raises(ValueError, match='不允许通过 kwargs 传递 lifespan'):
            create_app(lifespan=lambda app: app)

    def test_lifespan_context_is_set(self):
        from fastapi_augment.lifespan import fastapi_lifespan
        app = create_app()
        assert app.router.lifespan_context is fastapi_lifespan


# ── registries 规范化 ─────────────────────────────────────────────────

class TestResolveRegistries:

    def test_none_returns_empty(self):
        assert _resolve_registries(None) == []

    def test_single_registry_wrapped(self):
        reg = HookRegistry()
        result = _resolve_registries(reg)
        assert result == [reg]

    def test_list_passthrough(self):
        r1, r2 = HookRegistry(), HookRegistry()
        result = _resolve_registries([r1, r2])
        assert result == [r1, r2]


# ── 路由注册 ──────────────────────────────────────────────────────────

class TestCreateAppRouters:

    def test_include_plain_router(self):
        router = APIRouter()

        @router.get('/test')
        async def test_endpoint():
            return {'ok': True}

        app = create_app(routers=[router])
        client = TestClient(app)
        resp = client.get('/test')
        assert resp.status_code == 200
        assert resp.json() == {'ok': True}

    def test_include_router_with_kwargs(self):
        router = APIRouter()

        @router.get('/item')
        async def item_endpoint():
            return {'item': True}

        app = create_app(routers=[(router, {'prefix': '/api'})])
        client = TestClient(app)
        resp = client.get('/api/item')
        assert resp.status_code == 200

    def test_invalid_router_type_raises(self):
        with pytest.raises(TypeError, match='routers 元素必须为'):
            create_app(routers=['not_a_router'])

    def test_route_registrars(self):
        called = []

        def registrar(app: FastAPI):
            called.append(app)

        app = create_app(route_registrars=[registrar])
        assert len(called) == 1
        assert called[0] is app


# ── app.state 挂载 ────────────────────────────────────────────────────

class TestCreateAppState:

    def test_registries_on_state(self):
        reg = HookRegistry()
        app = create_app(registries=reg)
        assert app.state.registries == [reg]

    def test_engine_manager_on_state(self):
        fake_manager = object()
        app = create_app(engine_manager=fake_manager)
        assert app.state.engine_manager is fake_manager

    def test_session_factory_on_state(self):
        fake_factory = object()
        app = create_app(session_factory=fake_factory)
        assert app.state.session_factory is fake_factory

    def test_no_db_components_by_default(self):
        app = create_app()
        assert not hasattr(app.state, 'engine_manager')
        assert not hasattr(app.state, 'session_factory')


# ── RequestId 中间件 ──────────────────────────────────────────────────

class TestCreateAppMiddleware:

    def test_request_id_header_injected(self):
        app = create_app()

        @app.get('/ping')
        async def ping():
            return {'pong': True}

        client = TestClient(app)
        resp = client.get('/ping')
        assert 'x-request-id' in resp.headers
        assert len(resp.headers['x-request-id']) > 0

    def test_request_id_preserved_from_client(self):
        app = create_app()

        @app.get('/ping')
        async def ping():
            return {'pong': True}

        client = TestClient(app)
        resp = client.get('/ping', headers={'X-Request-Id': 'my-custom-id'})
        assert resp.headers['x-request-id'] == 'my-custom-id'


# ── CORS 配置 ─────────────────────────────────────────────────────────

class TestCreateAppCORS:

    def test_cors_enabled(self):
        app = create_app(cors_allow_origins=['http://localhost:3000'])
        # CORSMiddleware 被添加到中间件栈，通过 OPTIONS 请求验证
        client = TestClient(app)
        resp = client.options(
            '/',
            headers={
                'Origin': 'http://localhost:3000',
                'Access-Control-Request-Method': 'GET',
            }
        )
        assert 'access-control-allow-origin' in resp.headers

    def test_cors_disabled_by_default(self):
        app = create_app()
        client = TestClient(app)
        resp = client.options(
            '/',
            headers={
                'Origin': 'http://localhost:3000',
                'Access-Control-Request-Method': 'GET',
            }
        )
        assert 'access-control-allow-origin' not in resp.headers


# ── 健康检查开关 ─────────────────────────────────────────────────────

class TestHealthCheckToggle:

    def test_health_check_disabled_by_default(self):
        """默认不注册健康检查端点"""
        app = create_app()
        client = TestClient(app)
        resp = client.get('/health')
        assert resp.status_code == 404

    def test_health_check_enabled(self):
        """health_check=True 注册端点，无数据库时返回 healthy"""
        app = create_app(health_check=True)
        client = TestClient(app)

        resp = client.get('/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'healthy'
        assert any(c['name'] == 'app' for c in data['checks'])

    def test_health_check_sets_start_time(self):
        """health_check=True 时设置 start_time"""
        app = create_app(health_check=True)
        assert hasattr(app.state, 'start_time')
        assert app.state.start_time > 0

    def test_health_check_with_db_no_engine(self):
        """health_check=True 但无 engine_manager 时，数据库检查返回 unhealthy"""
        app = create_app(health_check=True)
        client = TestClient(app)

        resp = client.get('/health')
        # 无 engine_manager，include_db_check=False，所以只有 app 检查
        assert resp.status_code == 200
        data = resp.json()
        assert len(data['checks']) == 1
