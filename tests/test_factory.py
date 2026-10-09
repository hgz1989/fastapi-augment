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
        assert app.version == '0.2.0'
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

    def test_docs_logo_injects_x_logo(self):
        """create_app 传 docs_logo 后，OpenAPI info.x-logo 注入（ReDoc 生效）"""
        app = create_app(docs_logo='data:image/png;base64,AAAA')
        schema = app.openapi()
        assert schema is not None
        assert schema['info']['x-logo']['url'] == 'data:image/png;base64,AAAA'

    def test_docs_logo_default_no_injection(self, monkeypatch):
        """未传 docs_logo 且包内无 logo.png 时，不注入 x-logo（行为与旧版一致）"""
        monkeypatch.setattr(
            'fastapi_augment.factory.package_asset_data_uri',
            lambda *args, **kwargs: None,
        )
        app = create_app()
        schema = app.openapi()
        assert schema is not None
        assert 'x-logo' not in schema['info']

    def test_docs_logo_local_path(self, tmp_path):
        """docs_logo 传本地路径时转为 data URI 注入"""
        logo_file = tmp_path / 'logo.png'
        logo_file.write_bytes(b'\x89PNG\x0d\x0a\x1a\x0a')
        app = create_app(docs_logo=logo_file)
        schema = app.openapi()
        assert schema is not None
        uri = schema['info']['x-logo']['url']
        assert uri.startswith('data:image/png;base64,')

    def test_docs_logo_url_passthrough(self):
        """docs_logo 传 http URL 时原样使用（不转 data URI）"""
        app = create_app(docs_logo='https://example.com/logo.png')
        schema = app.openapi()
        assert schema is not None
        assert schema['info']['x-logo']['url'] == 'https://example.com/logo.png'

    def test_docs_auth_secret_from_env(self, monkeypatch):
        """docs_auth_secret 未传时回退环境变量 DOCS_AUTH_SECRET"""
        monkeypatch.setenv('DOCS_AUTH_SECRET', 'env-secret-123')
        app = create_app(
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
        )
        # 环境变量密钥应能正常完成登录（Cookie 签发依赖该密钥）
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret', 'next': '/docs'},
            follow_redirects=False,
        )
        assert resp.status_code == 303  # 登录成功跳转

    def test_docs_auth_random_secret_fallback(self, monkeypatch):
        """无显式/环境变量密钥时随机生成（重启后登录态失效，行为可用）"""
        monkeypatch.delenv('DOCS_AUTH_SECRET', raising=False)
        app = create_app(
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
        )
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret', 'next': '/docs'},
            follow_redirects=False,
        )
        assert resp.status_code == 303


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


# ── Docs 密钥多进程共享 ──────────────────────────────────────────────

class TestDocsSecretSharedFile:
    """docs_auth_secret 随机回退：密钥经临时文件在同机多进程间共享"""

    def test_same_cache_key_shares_secret(self, monkeypatch, tmp_path):
        """同一应用（相同 cache_key）多次解析得到同一密钥（模拟多 worker）"""
        import tempfile

        from fastapi_augment.factory import _resolve_docs_secret

        monkeypatch.delenv('DOCS_AUTH_SECRET', raising=False)
        monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))

        key = 'MyApp:[{"username": "admin", "password": "secret"}]'
        s1 = _resolve_docs_secret(None, cache_key=key)
        s2 = _resolve_docs_secret(None, cache_key=key)
        assert s1 == s2
        assert len(s1) == 64

    def test_different_cache_key_isolated(self, monkeypatch, tmp_path):
        """不同应用（不同 cache_key）密钥互相隔离"""
        import tempfile

        from fastapi_augment.factory import _resolve_docs_secret

        monkeypatch.delenv('DOCS_AUTH_SECRET', raising=False)
        monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))

        s1 = _resolve_docs_secret(None, cache_key='app-a')
        s2 = _resolve_docs_secret(None, cache_key='app-b')
        assert s1 != s2

    def test_existing_valid_file_reused(self, monkeypatch, tmp_path):
        """已存在的有效密钥文件被直接复用（第二个进程启动时读取）"""
        import hashlib
        import tempfile

        from fastapi_augment.factory import _resolve_docs_secret

        monkeypatch.delenv('DOCS_AUTH_SECRET', raising=False)
        monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))

        preset = 'a' * 64
        digest = hashlib.sha256(b'app-x').hexdigest()[:16]
        (tmp_path / f'fastapi-augment-docs-secret-{digest}').write_text(preset)
        assert _resolve_docs_secret(None, cache_key='app-x') == preset

    def test_invalid_file_content_regenerates(self, monkeypatch, tmp_path):
        """残留的无效密钥文件（空内容）触发重新生成而不是读入垃圾值"""
        import hashlib
        import tempfile

        from fastapi_augment.factory import _resolve_docs_secret

        monkeypatch.delenv('DOCS_AUTH_SECRET', raising=False)
        monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))

        digest = hashlib.sha256(b'app-y').hexdigest()[:16]
        (tmp_path / f'fastapi-augment-docs-secret-{digest}').write_text('')
        secret = _resolve_docs_secret(None, cache_key='app-y')
        assert len(secret) == 64

    def test_env_var_wins_over_file(self, monkeypatch, tmp_path):
        """配置了 DOCS_AUTH_SECRET 时不读共享文件"""
        import tempfile

        from fastapi_augment.factory import _resolve_docs_secret

        monkeypatch.setenv('DOCS_AUTH_SECRET', 'env-secret-123')
        monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))
        assert _resolve_docs_secret(None, cache_key='app-x') == 'env-secret-123'

    def test_two_apps_share_cookie_across_workers(self, monkeypatch, tmp_path):
        """端到端：同标题同凭证的两个 app 实例共享密钥，Cookie 互通"""
        import tempfile

        monkeypatch.delenv('DOCS_AUTH_SECRET', raising=False)
        monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))

        credentials = [{'username': 'admin', 'password': 'secret'}]
        app_a = create_app(title='SharedApp', docs_credentials=credentials)
        app_b = create_app(title='SharedApp', docs_credentials=credentials)

        client_a = TestClient(app_a)
        resp = client_a.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret', 'next': '/docs'},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        cookie = resp.cookies.get('docs_auth')
        assert cookie

        # app_a 签发的 Cookie 在 app_b（另一"进程"）上直接放行
        client_b = TestClient(app_b, cookies={'docs_auth': cookie})
        resp_b = client_b.get('/docs')
        assert resp_b.status_code == 200
