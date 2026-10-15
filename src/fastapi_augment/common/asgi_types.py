"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : ASGI 类型定义与运行时判定

类型定义遵循 ASGI 规范（asgi.readthedocs.io），仅支持 ASGI3
（可调用对象，调用签名 (scope, receive, send)）：
- 挂载消费方（Starlette ``mount`` 等）只接受三参可调用，ASGI2 类形态
  挂载后首个请求即 TypeError；现代框架（FastAPI / Starlette / Litestar /
  Quart）清一色 ASGI3，ASGI2 属历史过渡协议，不再支持
- Scope 与事件使用 MutableMapping —— 与 starlette.types（Scope/Message）
  对齐：Starlette 的 ASGIApp 形参即 MutableMapping，若此处用 dict，
  参数逆变会使应用无法赋给 mount() 等 ASGI 接口
- 事件保持宽松 MutableMapping —— 精确事件联合需要逐事件 TypedDict
  （可参考 asgiref 官方 types.py），且过严会误伤框架自定义消息

is_asgi_app 提供运行时近似判定：以 callable 为硬门槛（与 uvicorn
Config.load 一致），签名可解析时进一步检查 ASGI3 三参结构
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from inspect import isclass, isfunction, ismethod, signature, Parameter
from typing import Any, TypeGuard

Scope = MutableMapping[str, Any]
"""ASGI scope：连接与请求元数据（可被框架扩展）"""

ASGIReceiveEvent = MutableMapping[str, Any]
"""ASGI receive 事件：请求 / 断开 / 连接消息"""

ASGISendEvent = MutableMapping[str, Any]
"""ASGI send 事件：响应 / websocket / lifespan 消息"""

ASGIReceiveCallable = Callable[[], Awaitable[ASGIReceiveEvent]]
"""receive 可调用：等待接收一个 ASGI 事件"""

ASGISendCallable = Callable[[ASGISendEvent], Awaitable[None]]
"""send 可调用：发送一个 ASGI 事件"""

ASGI3Application = Callable[[Scope, ASGIReceiveCallable, ASGISendCallable], Awaitable[None]]
"""ASGI3 应用：以 (scope, receive, send) 调用的可调用对象"""


def is_asgi_app(app: Any) -> TypeGuard[ASGI3Application]:
    """运行时近似判定对象是否为可调用的 ASGI3 应用

    判定规则：
    1. callable 为硬门槛（与 uvicorn Config.load 一致）
    2. 签名可解析时，检查 ASGI3（3 个位置参数 scope / receive / send）
       结构；类形态（uvicorn 自动判定为 ASGI2）与单参形态一律拒绝
    3. 签名不可解析（C 扩展、部分包装器）时退回 callable 判定

    Args:
        app: 待判定的对象

    Returns:
        True 表示可视为 ASGI 应用，类型检查时收窄为 ASGI3Application；
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
    return len(positional) == 3
