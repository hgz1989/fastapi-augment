"""
common.exception_handlers 模块测试 — 全局统一异常处理器
"""
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.testclient import TestClient

from fastapi_augment.common.exception_handlers import (
    register_exception_handlers
)
from fastapi_augment.common.exceptions import (
    UnauthorizedError,
    TooManyRequestsError,
    BadRequestError,
    NotFoundError
)


# ── 测试辅助 ──────────────────────────────────────────────────────────

def _make_app() -> FastAPI:
    """创建注册了异常处理器的测试应用"""
    app = FastAPI()
    register_exception_handlers(app)
    return app


# ── BaseHttpError 处理器 ──────────────────────────────────────────────

class TestBaseHttpErrorHandler:

    def test_bad_request(self):
        app = _make_app()

        @app.get('/bad')
        async def bad():
            raise BadRequestError()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/bad')
        assert resp.status_code == 400
        body = resp.json()
        assert body['code'] == 400
        assert body['message'] == 'Bad request'
        assert body['data'] is None

    def test_not_found_with_custom_detail(self):
        app = _make_app()

        @app.get('/missing')
        async def missing():
            raise NotFoundError(detail='用户不存在')

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/missing')
        assert resp.status_code == 404
        body = resp.json()
        assert body['code'] == 404
        assert body['message'] == '用户不存在'

    def test_unauthorized(self):
        app = _make_app()

        @app.get('/auth')
        async def auth():
            raise UnauthorizedError()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/auth')
        assert resp.status_code == 401
        body = resp.json()
        assert body['code'] == 401
        assert body['message'] == 'Unauthorized'

    def test_too_many_requests_with_retry_after(self):
        app = _make_app()

        @app.get('/limited')
        async def limited():
            raise TooManyRequestsError(retry_after=30)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/limited')
        assert resp.status_code == 429
        assert resp.headers.get('retry-after') == '30'
        body = resp.json()
        assert body['code'] == 429

    def test_response_has_request_id(self):
        app = _make_app()

        @app.get('/err')
        async def err():
            raise BadRequestError()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/err')
        body = resp.json()
        assert 'requestId' in body


# ── 通用 HTTPException 处理器 ─────────────────────────────────────────

class TestHttpExceptionHandler:

    def test_fastapi_http_exception(self):
        """FastAPI 内部抛出的 HTTPException（如 HTTPException(403)）也被统一格式化"""
        from fastapi import HTTPException
        app = _make_app()

        @app.get('/forbidden')
        async def forbidden():
            raise HTTPException(status_code=403, detail='禁止访问')

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/forbidden')
        assert resp.status_code == 403
        body = resp.json()
        assert body['code'] == 403
        assert body['message'] == '禁止访问'

    def test_non_string_detail(self):
        """detail 不是字符串时，自动转为 str"""
        from fastapi import HTTPException
        app = _make_app()

        @app.get('/weird')
        async def weird():
            raise HTTPException(status_code=500, detail={'error': 'something'})

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/weird')
        body = resp.json()
        assert body['code'] == 500
        assert 'something' in body['message']


# ── 请求校验异常处理器 ────────────────────────────────────────────────

class TestValidationExceptionHandler:

    def test_missing_required_field(self):
        app = _make_app()

        class Item(BaseModel):
            name: str
            price: float

        @app.post('/items')
        async def create_item(item: Item):
            return item

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post('/items', json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body['code'] == 422
        assert body['message'] == '请求参数校验失败'
        assert 'errors' in body['extra']
        assert len(body['extra']['errors']) > 0

    def test_wrong_type(self):
        app = _make_app()

        class Item(BaseModel):
            price: float

        @app.post('/items')
        async def create_item(item: Item):
            return item

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post('/items', json={'price': 'not_a_number'})
        assert resp.status_code == 422
        body = resp.json()
        errors = body['extra']['errors']
        assert any('price' in e['field'] for e in errors)

    def test_error_detail_structure(self):
        """校验错误详情包含 field / message / type"""
        app = _make_app()

        class Item(BaseModel):
            name: str

        @app.post('/items')
        async def create_item(item: Item):
            return item

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post('/items', json={})
        body = resp.json()
        error = body['extra']['errors'][0]
        assert 'field' in error
        assert 'message' in error
        assert 'type' in error


# ── 未知异常处理器 ────────────────────────────────────────────────────

class TestGeneralExceptionHandler:

    def test_unhandled_exception_returns_500(self):
        app = _make_app()

        @app.get('/crash')
        async def crash():
            raise RuntimeError('数据库连接失败')

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/crash')
        assert resp.status_code == 500
        body = resp.json()
        assert body['code'] == 500
        assert body['message'] == '服务器内部错误'
        # 不应暴露内部异常细节
        assert '数据库连接失败' not in resp.text

    def test_unhandled_type_error(self):
        app = _make_app()

        @app.get('/type_err')
        async def type_err():
            return 'string' + 123

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/type_err')
        assert resp.status_code == 500
        body = resp.json()
        assert body['code'] == 500


# ── register_exception_handlers ───────────────────────────────────────

class TestRegisterExceptionHandlers:

    def test_register_on_app(self):
        app = FastAPI()
        register_exception_handlers(app)
        # 验证处理器已注册（FastAPI 内部用 exception_handlers dict 存储）
        from fastapi.exceptions import RequestValidationError
        from starlette.exceptions import HTTPException

        from fastapi_augment.common.exceptions import BaseHttpError

        assert BaseHttpError in app.exception_handlers
        assert HTTPException in app.exception_handlers
        assert RequestValidationError in app.exception_handlers
        assert Exception in app.exception_handlers


# ── 工厂自动装配 ──────────────────────────────────────────────────────

class TestFactoryIntegration:

    def test_create_app_auto_registers_handlers(self):
        """create_app 默认自动注册异常处理器"""
        from fastapi_augment import create_app
        from fastapi.exceptions import RequestValidationError
        from starlette.exceptions import HTTPException

        from fastapi_augment.common.exceptions import BaseHttpError

        app = create_app()
        assert BaseHttpError in app.exception_handlers
        assert HTTPException in app.exception_handlers
        assert RequestValidationError in app.exception_handlers
        assert Exception in app.exception_handlers

    def test_create_app_disable_exceptions(self):
        """register_exceptions=False 禁用自动注册"""
        from fastapi_augment import create_app
        from fastapi_augment.common.exceptions import BaseHttpError

        app = create_app(register_exceptions=False)
        assert BaseHttpError not in app.exception_handlers

    def test_factory_end_to_end(self):
        """工厂创建的 app 抛出业务异常，返回统一格式"""
        from fastapi_augment import create_app
        from fastapi_augment.common.exceptions import NotFoundError

        app = create_app()

        @app.get('/user')
        async def get_user():
            raise NotFoundError(detail='用户不存在')

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/user')
        assert resp.status_code == 404
        body = resp.json()
        assert body['code'] == 404
        assert body['message'] == '用户不存在'
        assert 'requestId' in body


# ── common 模块导入 ───────────────────────────────────────────────────

class TestCommonImports:

    def test_import_exceptions_from_common(self):
        """异常类可从 common 模块导入"""
        from fastapi_augment.common import (
            BadRequestError,
            NotFoundError,
        )
        assert BadRequestError is not None
        assert NotFoundError is not None

    def test_import_register_from_common(self):
        """register_exception_handlers 可从 common 模块导入"""
        from fastapi_augment.common import register_exception_handlers
        assert callable(register_exception_handlers)
