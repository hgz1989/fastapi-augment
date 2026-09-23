"""
@Author         : hangu
@CreateDate     : 2026/9/4
@Description    : 通用模块 — 异常 / 异常处理器 / 常量
"""
from .app_discovery import (
    FastAPIAppSpec,
    discover_fastapi_apps,
    validate_asgi_import
)
from .asgi_types import (
    ASGI2Application,
    ASGI2Protocol,
    ASGI3Application,
    ASGIApplication,
    ASGIReceiveCallable,
    ASGIReceiveEvent,
    ASGISendCallable,
    ASGISendEvent,
    Scope,
    is_asgi_app
)
from .constants import DEFAULT_ERR_MSG
from .exception_handlers import (
    base_http_error_handler,
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
    register_exception_handlers
)
from .exceptions import (
    BaseHttpError,
    BadRequestError,
    UnauthorizedError,
    PaymentRequiredError,
    ForbiddenError,
    NotFoundError,
    MethodNotAllowedError,
    NotAcceptableError,
    RequestTimeoutError,
    ConflictError,
    GoneError,
    PreconditionFailedError,
    PayloadTooLargeError,
    URITooLongError,
    UnsupportedMediaTypeError,
    LockedError,
    TooManyRequestsError
)

__all__ = [
    # app_discovery
    'FastAPIAppSpec',
    'discover_fastapi_apps',
    'validate_asgi_import',
    # asgi_types
    'ASGI2Application',
    'ASGI2Protocol',
    'ASGI3Application',
    'ASGIApplication',
    'ASGIReceiveCallable',
    'ASGIReceiveEvent',
    'ASGISendCallable',
    'ASGISendEvent',
    'Scope',
    'is_asgi_app',
    # constants
    'DEFAULT_ERR_MSG',
    # exceptions
    'BaseHttpError',
    'BadRequestError',
    'UnauthorizedError',
    'PaymentRequiredError',
    'ForbiddenError',
    'NotFoundError',
    'MethodNotAllowedError',
    'NotAcceptableError',
    'RequestTimeoutError',
    'ConflictError',
    'GoneError',
    'PreconditionFailedError',
    'PayloadTooLargeError',
    'URITooLongError',
    'UnsupportedMediaTypeError',
    'LockedError',
    'TooManyRequestsError',
    # exception handlers
    'base_http_error_handler',
    'http_exception_handler',
    'validation_exception_handler',
    'general_exception_handler',
    'register_exception_handlers'
]
