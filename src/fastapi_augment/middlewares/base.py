"""
@Author         : hangu
@CreateDate     : 2026/9/4
@Description    : 通用ASGI中间件基类
"""
from contextvars import Token

from starlette.types import (
    ASGIApp,
    Scope,
    Message,
    Receive,
    Send
)


class BaseASGIMiddleware:
    """
    原生ASGI中间件抽象基类
    剥离重复ASGI样板代码，子类只实现钩子即可
    兼容 http / websocket；http支持包装send修改响应头；finally保证清理
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def on_request(self, scope: Scope) -> Token | None:
        """请求进入钩子：http/websocket都会调用

        返回token，如果使用ContextVar，返回set得到的token；没有返回None

        Args:
            scope: ASGI scope对象

        Returns:
            ContextVar token或None
        """
        return None

    async def wrap_send(self, message: Message) -> Message:
        """http.response.start消息钩子，可以修改headers等

        返回修改后的message对象
        仅HTTP模式生效；websocket不会进入此逻辑
        默认实现直接返回原message，子类按需覆盖
        （保留self参数，子类覆盖时需要访问实例属性）

        Args:
            message: ASGI message对象

        Returns:
            修改后的message对象
        """
        return message

    async def on_finish(self, token: Token | None) -> None:
        """请求结束finally钩子，用于reset ContextVar等清理工作

        Args:
            token: ContextVar token或None

        空实现：子类按需覆盖
        """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope['type']

        if scope_type not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return

        token: Token | None = await self.on_request(scope)

        try:
            if scope_type == 'http':
                async def send_wrapper(message: Message) -> None:
                    if message['type'] == 'http.response.start':
                        message = await self.wrap_send(message)
                    await send(message)

                await self.app(scope, receive, send_wrapper)
            else:
                # websocket，不包装send，只执行上下文
                await self.app(scope, receive, send)
        finally:
            await self.on_finish(token)
