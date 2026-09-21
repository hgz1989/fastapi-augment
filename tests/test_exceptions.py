"""
common.exceptions 模块测试 — 业务异常类
"""
import pytest
from starlette import status

from fastapi_augment.common.constants import (
    DEFAULT_ERR_MSG
)
from fastapi_augment.common.exceptions import (
    BaseHttpError,
    PaymentRequiredError,
    MethodNotAllowedError,
    NotAcceptableError,
    RequestTimeoutError,
    GoneError,
    PreconditionFailedError,
    PayloadTooLargeError,
    URITooLongError,
    UnsupportedMediaTypeError,
    LockedError,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
    TooManyRequestsError
)


# ── BaseHttpError ─────────────────────────────────────────────────────

class TestBaseHttpError:

    def test_default_message_from_constants(self):
        err = BaseHttpError(status.HTTP_400_BAD_REQUEST)
        assert err.status_code == 400
        assert err.detail == 'Bad request'

    def test_custom_detail(self):
        err = BaseHttpError(status.HTTP_404_NOT_FOUND, detail='资源不存在')
        assert err.detail == '资源不存在'

    def test_custom_headers(self):
        err = BaseHttpError(status.HTTP_401_UNAUTHORIZED, headers={'WWW-Authenticate': 'Bearer'})
        assert err.headers == {'WWW-Authenticate': 'Bearer'}

    def test_undefined_status_code_raises_key_error(self):
        with pytest.raises(KeyError, match='not defined'):
            BaseHttpError(999)

    def test_none_detail_uses_default(self):
        err = BaseHttpError(status.HTTP_403_FORBIDDEN, detail=None)
        assert err.detail == 'Forbidden'


# ── 各子类状态码验证 ──────────────────────────────────────────────────

class TestExceptionSubclasses:

    @pytest.mark.parametrize('exc_cls,expected_code', [
        (BadRequestError, 400),
        (UnauthorizedError, 401),
        (PaymentRequiredError, 402),
        (ForbiddenError, 403),
        (NotFoundError, 404),
        (MethodNotAllowedError, 405),
        (NotAcceptableError, 406),
        (RequestTimeoutError, 408),
        (ConflictError, 409),
        (GoneError, 410),
        (PreconditionFailedError, 412),
        (PayloadTooLargeError, 413),
        (URITooLongError, 414),
        (UnsupportedMediaTypeError, 415),
        (LockedError, 423),
        (TooManyRequestsError, 429),
    ])
    def test_status_code(self, exc_cls, expected_code):
        err = exc_cls()
        assert err.status_code == expected_code

    @pytest.mark.parametrize('exc_cls', [
        BadRequestError,
        UnauthorizedError,
        ForbiddenError,
        NotFoundError,
        ConflictError,
    ])
    def test_default_message(self, exc_cls):
        err = exc_cls()
        assert err.detail == DEFAULT_ERR_MSG[err.status_code]

    @pytest.mark.parametrize('exc_cls', [
        BadRequestError,
        UnauthorizedError,
        ForbiddenError,
        NotFoundError,
    ])
    def test_custom_message(self, exc_cls):
        err = exc_cls(detail='自定义错误')
        assert err.detail == '自定义错误'

    @pytest.mark.parametrize('exc_cls', [
        BadRequestError,
        NotFoundError,
    ])
    def test_custom_headers(self, exc_cls):
        err = exc_cls(headers={'X-Custom': 'value'})
        assert err.headers == {'X-Custom': 'value'}


# ── TooManyRequestsError 特殊逻辑 ─────────────────────────────────────

class TestTooManyRequestsError:

    def test_retry_after_header(self):
        err = TooManyRequestsError(retry_after=60)
        assert err.status_code == 429
        assert err.headers is not None
        assert err.headers['Retry-After'] == '60'

    def test_retry_after_with_custom_headers(self):
        err = TooManyRequestsError(retry_after=30, headers={'X-RateLimit': '100'})
        assert err.headers['Retry-After'] == '30'
        assert err.headers['X-RateLimit'] == '100'

    def test_no_retry_after(self):
        err = TooManyRequestsError()
        assert err.status_code == 429
        assert err.headers is None

    def test_custom_detail(self):
        err = TooManyRequestsError(detail='请求太频繁')
        assert err.detail == '请求太频繁'

    def test_custom_status_code(self):
        """status_code 参数可覆盖子类默认的 429"""
        err = TooManyRequestsError(status_code=400, detail='受限')
        assert err.status_code == 400
        assert err.detail == '受限'

    def test_status_code_defaults_to_429(self):
        err = TooManyRequestsError()
        assert err.status_code == 429
