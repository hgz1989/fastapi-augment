"""
@Author         : zarkhan
@CreateDate     : 2026/7/4
@Description    : Request-ID 追踪 ASGI 中间件与上下文工具
"""
from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.types import Scope, Message

from .base import BaseASGIMiddleware

request_id_ctx_var: ContextVar[str | None] = ContextVar('request_id', default=None)


def get_request_id() -> str | None:
    """获取当前请求的Request ID

    Returns:
        Request ID or None
    """
    return request_id_ctx_var.get()


def set_request_id(request_id: str) -> Token:
    """设置当前请求的Request ID，返回token用于请求结束重置上下文

    Args:
        request_id: Request ID

    Returns:
        用于请求结束重置上下文的token
    """
    return request_id_ctx_var.set(request_id)


def reset_request_id(token: Token) -> None:
    """重置当前请求的Request ID

    Args:
        token: 用于重置上下文的token
    """
    request_id_ctx_var.reset(token)


class RequestIdMiddleware(BaseASGIMiddleware):
    """Request‑ID追踪中间件，继承通用ASGI基类"""

    async def on_request(self, scope: Scope) -> Token | None:
        # 1. 从请求头提取X‑Request‑Id
        request_id = None

        for name, value in scope.get('headers', []):
            if name == b'x-request-id':
                request_id = value.decode('latin-1')
                break

        if not request_id:
            request_id = str(uuid4())

        return set_request_id(request_id)

    async def wrap_send(self, message: Message) -> Message:
        """注入响应头 X‑Request‑Id"""
        req_id = get_request_id()

        if not req_id:
            return message

        headers = list(message.get('headers', []))

        if not any(k == b'x-request-id' for k, _ in headers):
            headers.append((b'x-request-id', req_id.encode('latin-1')))

        message['headers'] = headers
        return message

    async def on_finish(self, token: Token | None) -> None:
        """请求结束重置上下文，防止泄漏串请求"""
        if token is not None:
            reset_request_id(token)
