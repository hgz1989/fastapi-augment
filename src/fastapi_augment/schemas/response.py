"""
@Author         : hangu
@CreateDate     : 2026/9/1
@Description    : 统一API响应模型与工厂函数
"""
from __future__ import annotations

from typing import Generic, cast, overload

from pydantic import Field

from .base import SchemaBase
from .types import T, E

CODE_SUCCESS = 0

# ====================== request_id 默认值 ======================
def _default_request_id() -> str:
    """获取当前请求ID，无请求上下文返回空字符串

    Returns:
        请求ID
    """
    # 延迟导入，避免循环依赖
    from ..middlewares import get_request_id
    return get_request_id() or ''


# ====================== API响应模型 ======================
class APIResponse(SchemaBase, Generic[T, E]):
    """全局统一返回格式

    request_id: 自动从 ContextVar 获取当前请求ID；无请求上下文返回空字符串
    """
    request_id: str = Field(default_factory=_default_request_id, description='请求唯一追踪ID')
    code: int = Field(default=CODE_SUCCESS, description='业务码，0代表成功')
    message: str = Field(default='操作成功', description='提示文案')
    data: T | None = Field(default=None, description='业务主体数据')
    extra: E | None = Field(default=None, description='扩展附加信息')


# ====================== 工厂函数 overload 重载，优化IDE泛型推导 ======================
@overload
def build_response(*, code: int = CODE_SUCCESS, message: str = '操作成功') -> APIResponse[None, None]: ...


@overload
def build_response(*, code: int = CODE_SUCCESS, message: str = '操作成功', data: T) -> APIResponse[T, None]: ...


@overload
def build_response(*, code: int = CODE_SUCCESS, message: str = '操作成功', extra: E) -> APIResponse[None, E]: ...


@overload
def build_response(*, code: int = CODE_SUCCESS, message: str = '操作成功', data: T, extra: E) -> APIResponse[T, E]: ...


def build_response(
        *,
        code: int = CODE_SUCCESS,
        message: str = '操作成功',
        data: T | None = None,
        extra: E | None = None,
) -> APIResponse[T, E]:
    """底层构建响应，优先使用 response_success / response_fail

    Args:
        code: 业务码，0代表成功
        message: 提示文案
        data: 业务主体数据
        extra: 扩展附加信息

    Returns:
        APIResponse[T, E]
    """
    return APIResponse(code=code, message=message, data=data, extra=extra)


@overload
def response_success(*, message: str = '操作成功') -> APIResponse[None, None]: ...


@overload
def response_success(*, message: str = '操作成功', data: T) -> APIResponse[T, None]: ...


@overload
def response_success(*, message: str = '操作成功', extra: E) -> APIResponse[None, E]: ...


@overload
def response_success(*, message: str = '操作成功', data: T, extra: E) -> APIResponse[T, E]: ...


def response_success(
        *,
        message: str = '操作成功',
        data: T | None = None,
        extra: E | None = None,
) -> APIResponse[T, E]:
    """构造成功响应

    Args:
        message: 提示文案
        data: 业务主体数据
        extra: 扩展附加信息

    Returns:
        APIResponse[T, E]
    """
    return build_response(code=CODE_SUCCESS, message=message, data=cast(T, data), extra=cast(E, extra))


@overload
def response_fail(*, code: int, message: str = '操作失败') -> APIResponse[None, None]: ...


@overload
def response_fail(*, code: int, message: str = '操作失败', extra: E) -> APIResponse[None, E]: ...


def response_fail(
        *,
        code: int,
        message: str = '操作失败',
        extra: E | None = None,
) -> APIResponse[None, E]:
    """构造失败响应，给业务代码 & fastapi_handlers异常处理器使用

    Args:
        code: 业务码，0代表成功
        message: 提示文案
        extra: 扩展附加信息

    Returns:
        APIResponse[None, E]
    """
    return build_response(code=code, message=message, extra=cast(E, extra))
