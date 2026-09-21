"""
@Author         : hangu
@CreateDate     : 2026/9/4
@Description    : 全局统一异常处理器
                  - 将各类异常转换为统一的 APIResponse JSON 格式
                  - 提供 register_exception_handlers 一键注册到 FastAPI 应用
"""
from __future__ import annotations

from logging import getLogger

from fastapi import FastAPI
from fastapi.exceptions import (
    RequestValidationError
)
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

from .exceptions import BaseHttpError
from ..schemas.response import response_fail

_logger = getLogger(__name__)


# ===================== 业务异常处理器 =====================

async def base_http_error_handler(
        _request: Request,
        exc: BaseHttpError,
) -> JSONResponse:
    """处理 BaseHttpError 及其所有子类（统一业务异常）

    将业务异常转换为统一 APIResponse 格式，
    HTTP 状态码与 exc.status_code 一致，
    body.code 同样使用 HTTP 状态码，body.message 使用 exc.detail

    Args:
        _request: Starlette Request 对象
        exc: 业务异常实例

    Returns:
        统一格式的 JSON 响应
    """
    body = response_fail(code=exc.status_code, message=exc.detail or '请求错误')
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(mode='json', by_alias=True),
        headers=exc.headers,
    )


# ===================== 通用 HTTP 异常处理器 =====================

async def http_exception_handler(
        _request: Request,
        exc: HTTPException,
) -> JSONResponse:
    """处理 Starlette/FastAPI 原生 HTTPException

    覆盖 FastAPI 默认处理器，将响应格式统一为 APIResponse
    注意：BaseHttpError 继承自 HTTPException，但 FastAPI 会优先匹配
    更具体的处理器（base_http_error_handler），所以此处不会拦截业务异常

    Args:
        _request: Starlette Request 对象
        exc: HTTPException 实例

    Returns:
        统一格式的 JSON 响应
    """
    body = response_fail(
        code=exc.status_code,
        message=exc.detail if isinstance(exc.detail, str) else str(exc.detail or ''),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(mode='json', by_alias=True),
        headers=getattr(exc, 'headers', None),
    )


# ===================== 请求校验异常处理器 =====================

async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
) -> JSONResponse:
    """处理 Pydantic 请求参数校验异常（422）

    将校验错误详情提取到 extra.errors 中，方便前端定位具体字段

    Args:
        _request: Starlette Request 对象
        exc: RequestValidationError 实例

    Returns:
        统一格式的 JSON 响应（HTTP 422）
    """
    errors = []
    for error in exc.errors():
        field = ' -> '.join(str(loc) for loc in error['loc'])
        errors.append({
            'field': field,
            'message': error['msg'],
            'type': error['type'],
        })

    body = response_fail(
        code=422,
        message='请求参数校验失败',
        extra={'errors': errors},
    )
    return JSONResponse(
        status_code=422,
        content=body.model_dump(mode='json', by_alias=True),
    )


# ===================== 未知异常处理器 =====================

async def general_exception_handler(
        _request: Request,
        exc: Exception,
) -> JSONResponse:
    """处理所有未被捕获的异常（兜底）

    记录完整异常日志（含堆栈），但响应体只返回通用提示，
    避免将内部实现细节（堆栈、SQL 等）暴露给客户端

    Args:
        _request: Starlette Request 对象
        exc: 未捕获的异常实例

    Returns:
        统一格式的 JSON 响应（HTTP 500）
    """
    _logger.exception(f'[未捕获异常] {type(exc).__name__}: {exc}')
    body = response_fail(code=500, message='服务器内部错误')
    return JSONResponse(
        status_code=500,
        content=body.model_dump(mode='json', by_alias=True),
    )


# ===================== 一键注册 =====================

def register_exception_handlers(app: FastAPI) -> None:
    """将全部统一异常处理器注册到 FastAPI 应用

    注册后，以下异常会被转换为统一的 APIResponse 格式：
        - BaseHttpError 及子类 → 对应 HTTP 状态码
        - Starlette HTTPException → 对应 HTTP 状态码
        - RequestValidationError → HTTP 422 + 字段级错误详情
        - Exception（兜底） → HTTP 500

    注意：create_app 工厂默认自动调用本函数（register_exceptions=True），
    通常无需手动注册。仅在以下场景需要手动调用：
        - 未使用 create_app 工厂，自行构建 FastAPI 实例时
        - 传入 register_exceptions=False 禁用后，想选择性注册时

    Example::

        # 方式一：工厂自动注册（推荐）
        app = create_app(title='My Service')

        # 方式二：手动注册（未使用工厂时）
        from fastapi import FastAPI
        app = FastAPI()
        register_exception_handlers(app)

    Args:
        app: FastAPI 应用实例
    """
    # 注意注册顺序：BaseHttpError 必须在 HTTPException 之前注册，
    # 因为 BaseHttpError 继承自 HTTPException，FastAPI 优先匹配更具体的异常类型
    app.add_exception_handler(BaseHttpError, base_http_error_handler)  # type: ignore
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore
    app.add_exception_handler(Exception, general_exception_handler)  # type: ignore
