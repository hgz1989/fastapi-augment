"""
middlewares 模块测试 — BaseASGIMiddleware / RequestIdMiddleware
"""
import httpx2
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.types import Message

from fastapi_augment.middlewares import (
    BaseASGIMiddleware,
    RequestIdMiddleware,
    get_request_id,
    set_request_id,
    reset_request_id
)


# ── BaseASGIMiddleware ────────────────────────────────────────────────

class TestBaseASGIMiddleware:

    def test_passthrough_lifespan_scope(self):
        """非 http/websocket scope 直接透传"""
        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            return {'ok': True}

        app.add_middleware(BaseASGIMiddleware)
        client = TestClient(app)
        resp = client.get('/test')
        assert resp.status_code == 200

    async def test_on_request_called_for_http(self):
        """on_request 钩子在 http 请求时被调用"""
        called = []

        class TrackingMiddleware(BaseASGIMiddleware):
            async def on_request(self, scope):
                called.append(True)

        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            return {'ok': True}

        app.add_middleware(TrackingMiddleware)

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            resp = await client.get('/test')
            assert resp.status_code == 200
        assert len(called) == 1

    async def test_on_finish_called(self):
        """on_finish 在请求结束时被调用（finally）"""
        finished = []

        class TrackingMiddleware(BaseASGIMiddleware):
            async def on_request(self, scope):
                return None

            async def on_finish(self, token):
                finished.append(True)

        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            return {}

        app.add_middleware(TrackingMiddleware)

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            await client.get('/test')
        assert len(finished) == 1

    async def test_wrap_send_for_http_response_start(self):
        """wrap_send 仅拦截 http.response.start 消息"""
        wrapped = []

        class HeaderMiddleware(BaseASGIMiddleware):
            async def on_request(self, scope):
                return None

            async def wrap_send(self, message: Message) -> Message:
                wrapped.append(message['type'])
                return message

        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            return {'data': True}

        app.add_middleware(HeaderMiddleware)

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            await client.get('/test')
        assert 'http.response.start' in wrapped


# ── RequestIdMiddleware ───────────────────────────────────────────────

class TestRequestIdMiddleware:

    async def test_generates_request_id_when_absent(self):
        """无 X-Request-Id 头时自动生成"""
        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            return {}

        app.add_middleware(RequestIdMiddleware)

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            resp = await client.get('/test')
            assert 'x-request-id' in resp.headers
            assert len(resp.headers['x-request-id']) > 0

    async def test_preserves_client_request_id(self):
        """客户端传入的 X-Request-Id 被保留"""
        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            return {}

        app.add_middleware(RequestIdMiddleware)

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            resp = await client.get('/test', headers={'X-Request-Id': 'custom-123'})
            assert resp.headers['x-request-id'] == 'custom-123'

    async def test_context_var_set_during_request(self):
        """请求处理期间 ContextVar 可获取到 request_id"""
        captured_id = []
        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            captured_id.append(get_request_id())
            return {}

        app.add_middleware(RequestIdMiddleware)

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            await client.get('/test', headers={'X-Request-Id': 'ctx-test'})
        assert captured_id == ['ctx-test']

    async def test_context_var_reset_after_request(self):
        """请求结束后 ContextVar 被重置"""
        app = FastAPI()

        @app.get('/test')
        async def test_ep():
            return {}

        app.add_middleware(RequestIdMiddleware)

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url='http://test',
        ) as client:
            await client.get('/test')

        # 请求结束后，ContextVar 应回到默认值
        assert get_request_id() is None


# ── ContextVar 工具函数 ──────────────────────────────────────────────

class TestRequestIdContextVars:

    def test_get_request_id_default_none(self):
        assert get_request_id() is None

    def test_set_and_get_request_id(self):
        token = set_request_id('test-id')
        try:
            assert get_request_id() == 'test-id'
        finally:
            reset_request_id(token)

    def test_reset_request_id(self):
        token = set_request_id('temp-id')
        reset_request_id(token)
        assert get_request_id() is None
