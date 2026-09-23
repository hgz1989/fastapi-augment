"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : ASGI 类型定义与运行时判定

类型定义遵循 ASGI 规范（asgi.readthedocs.io）：
- ASGI2 应用为类，实例化时接收 scope（ASGI2Protocol）
- ASGI3 应用为可调用对象，调用签名 (scope, receive, send)
- ASGIReceiveEvent / ASGISendEvent 使用宽松 dict —— 精确事件联合
  需要逐事件 TypedDict（可参考 asgiref 官方 types.py），且过严会
  误伤框架自定义消息

is_asgi_app 提供运行时近似判定：以 callable 为硬门槛（与 uvicorn
Config.load 一致），签名可解析时进一步检查 ASGI2 / ASGI3 结构
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import isclass, isfunction, ismethod, signature, Parameter
from typing import Any, Protocol, TypeGuard

Scope = dict[str, Any]
"""ASGI scope：连接与请求元数据（可被框架扩展）"""

ASGIReceiveEvent = dict[str, Any]
"""ASGI receive 事件：请求 / 断开 / 连接消息"""

ASGISendEvent = dict[str, Any]
"""ASGI send 事件：响应 / websocket / lifespan 消息"""

ASGIReceiveCallable = Callable[[], Awaitable[ASGIReceiveEvent]]
"""receive 可调用：等待接收一个 ASGI 事件"""

ASGISendCallable = Callable[[ASGISendEvent], Awaitable[None]]
"""send 可调用：发送一个 ASGI 事件"""


class ASGI2Protocol(Protocol):
    """ASGI2 应用协议：类实例化时接收 scope，实例以 (receive, send) 调用"""

    def __init__(self, scope: Scope) -> None: ...

    async def __call__(self, receive: ASGIReceiveCallable, send: ASGISendCallable) -> None: ...


ASGI2Application = type[ASGI2Protocol]
"""ASGI2 应用：遵循 ASGI2Protocol 的类"""

ASGI3Application = Callable[[Scope, ASGIReceiveCallable, ASGISendCallable], Awaitable[None]]
"""ASGI3 应用：以 (scope, receive, send) 调用的可调用对象"""

ASGIApplication = ASGI2Application | ASGI3Application
"""ASGI 应用：ASGI2（类）与 ASGI3（可调用）的并集"""


def is_asgi_app(app: Any) -> TypeGuard[ASGIApplication]:
    """运行时近似判定对象是否为可调用的 ASGI 应用

    判定规则：
    1. callable 为硬门槛（与 uvicorn Config.load 一致）
    2. 签名可解析时，进一步检查 ASGI2（类，1 个位置参数 scope）或
       ASGI3（3 个位置参数 scope / receive / send）结构
    3. 签名不可解析（C 扩展、部分包装器）时退回 callable 判定

    Args:
        app: 待判定的对象

    Returns:
        True 表示可视为 ASGI 应用，类型检查时收窄为 ASGIApplication；
        签名判定为近似，权威判定以 uvicorn 实际启动为准
    """
    if not callable(app):
        return False
    try:
        if isclass(app):
            target = app.__init__
        elif isfunction(app) or ismethod(app):
            target = app
        else:
            target = type(app).__call__
        params = list(signature(target).parameters.values())
    except (TypeError, ValueError):
        return True
    if any(p.kind is Parameter.VAR_POSITIONAL for p in params):
        return True
    positional = [p for p in params
                  if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
                  and p.name not in ('self', 'cls')]
    return len(positional) in (1, 3)
