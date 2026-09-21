"""
@Author         : hangu
@CreateDate     : 2026/9/4
@Description    : 统一业务异常
"""
from typing import Any

from starlette import status
from starlette.exceptions import HTTPException

from .constants import DEFAULT_ERR_MSG


# ===================== 通用基类：统一封装 detail + headers 逻辑 =====================
class BaseHttpError(HTTPException):
    """统一HTTP异常基类，所有4xx异常继承此类，原生兼容starlette.HTTPException

    子类只需声明 ``_status_code`` 类变量，无需重写 __init__::

        class NotFoundError(BaseHttpError):
            _status_code = 404

        raise NotFoundError()                        # 使用默认文案
        raise NotFoundError(detail='用户不存在')       # 自定义提示

    Attributes:
        _status_code: 子类声明的HTTP状态码
        status_code: HTTP状态码（继承自HTTPException）
        detail: 异常提示文案
        headers: 响应附加http头
    """
    __slots__ = ()
    _status_code: int | None = None

    def __init__(
            self,
            status_code: int | None = None,
            detail: str | None = None,
            headers: dict[str, Any] | None = None,
    ):
        """初始化http业务异常

        Args:
            status_code: http响应状态码，不传则读取子类的 _status_code 类变量
            detail: 自定义错误提示，不传使用内置默认文案
            headers: 附加响应头

        Raises:
            KeyError: 传入未在DEFAULT_ERR_MSG定义的status_code
        """
        code = status_code if status_code is not None else self._status_code
        if code is None:
            raise TypeError(
                f'{type(self).__name__} 必须声明 _status_code 类变量或传入 status_code 参数'
            )
        if code not in DEFAULT_ERR_MSG:
            raise KeyError(f'status_code {code} not defined in DEFAULT_ERR_MSG')
        msg = detail or DEFAULT_ERR_MSG[code]
        super().__init__(status_code=code, detail=msg, headers=headers)


# ===================== 各类4xx异常子类（极简声明，无重复__init__） =====================
# 子类只需声明 _status_code 类变量，__init__ 由基类统一处理
class BadRequestError(BaseHttpError):
    """400 请求错误"""
    _status_code = status.HTTP_400_BAD_REQUEST


class UnauthorizedError(BaseHttpError):
    """401 未授权错误"""
    _status_code = status.HTTP_401_UNAUTHORIZED


class PaymentRequiredError(BaseHttpError):
    """402 需要付费错误"""
    _status_code = status.HTTP_402_PAYMENT_REQUIRED


class ForbiddenError(BaseHttpError):
    """403 禁止访问错误"""
    _status_code = status.HTTP_403_FORBIDDEN


class NotFoundError(BaseHttpError):
    """404 未找到资源"""
    _status_code = status.HTTP_404_NOT_FOUND


class MethodNotAllowedError(BaseHttpError):
    """405 请求方法不允许"""
    _status_code = status.HTTP_405_METHOD_NOT_ALLOWED


class NotAcceptableError(BaseHttpError):
    """406 客户端不支持返回格式"""
    _status_code = status.HTTP_406_NOT_ACCEPTABLE


class RequestTimeoutError(BaseHttpError):
    """408 请求超时"""
    _status_code = status.HTTP_408_REQUEST_TIMEOUT


class ConflictError(BaseHttpError):
    """409 资源冲突"""
    _status_code = status.HTTP_409_CONFLICT


class GoneError(BaseHttpError):
    """410 资源已永久删除"""
    _status_code = status.HTTP_410_GONE


class PreconditionFailedError(BaseHttpError):
    """412 前置校验失败"""
    _status_code = status.HTTP_412_PRECONDITION_FAILED


class PayloadTooLargeError(BaseHttpError):
    """413 请求体过大"""
    _status_code = status.HTTP_413_CONTENT_TOO_LARGE


class URITooLongError(BaseHttpError):
    """414 URI链接过长"""
    _status_code = status.HTTP_414_URI_TOO_LONG


class UnsupportedMediaTypeError(BaseHttpError):
    """415 不支持的请求媒体类型"""
    _status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


class LockedError(BaseHttpError):
    """423 资源锁定"""
    _status_code = status.HTTP_423_LOCKED


class TooManyRequestsError(BaseHttpError):
    """429 请求过于频繁（限流专用，支持retry_after快捷参数）"""
    _status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(
            self,
            status_code: int | None = None,
            detail: str | None = None,
            retry_after: int | None = None,
            headers: dict[str, Any] | None = None,
    ):
        """

        Args:
            status_code: http响应状态码，不传则读取子类的 _status_code 类变量
            detail: 自定义错误提示
            retry_after: 设置 Retry‑After 响应头，单位秒
            headers: 自定义附加响应头
        """
        final_headers: dict[str, Any] = dict(headers) if headers is not None else {}
        if retry_after is not None:
            final_headers['Retry-After'] = str(retry_after)
        super().__init__(
            status_code=status_code,
            detail=detail,
            headers=final_headers if final_headers else None,
        )
