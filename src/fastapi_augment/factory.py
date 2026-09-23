"""
@Author         : hangu
@CreateDate     : 2026/9/3
@Description    : FastAPI 应用工厂
                  - 统一创建 FastAPI 实例并自动装配生命周期、数据库、中间件、路由
                  - 支持可选的 SQLAlchemy 读写分离集成
                  - 通过 app.state 暴露核心组件供业务层使用
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from time import time
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, APIRouter
from starlette.middleware import Middleware

from .common.exception_handlers import (
    register_exception_handlers
)
from .health import create_health_router
from .lifespan import (
    fastapi_lifespan,
    HookRegistry
)
from .middlewares import RequestIdMiddleware
from .openapi import (
    configure_openapi_schema,
    OpenAPICustomConfig
)

if TYPE_CHECKING:
    from .db.sqlalchemy import EngineManager, SessionFactory

# -------------------------- 类型别名 --------------------------
# 路由注册回调：接收 app 实例，负责 include_router 等操作
_RouteRegistrar = Callable[[FastAPI], None]


def create_app(
        *,
        title: str = 'FastAPI Augment',
        summary: str = 'FastAPI Augment - Extended utilities and patterns for FastAPI',
        description: str = (
                'FastAPI Augment is a lightweight extension library for FastAPI that '
                'provides out-of-the-box solutions for common backend challenges. It '
                'includes asynchronous database session management (with read-write splitting), '
                'unified API response models, pagination helpers, and streamlined dependency '
                'injection for transactional operations. Designed to reduce boilerplate and '
                'enforce clean architecture, it accelerates the development of production-ready '
                'web services.'
        ),
        version: str = '0.1.6',
        debug: bool = False,
        docs_url: str | None = '/docs',
        redoc_url: str | None = '/redoc',
        openapi_url: str | None = '/openapi.json',
        # CORS配置：None=不启用；传入非空序列才启用CORS中间件
        cors_allow_origins: Sequence[str] | None = None,
        cors_allow_methods: Sequence[str] | None = None,
        cors_allow_headers: Sequence[str] | None = None,
        # 生命周期钩子
        registries: Sequence[HookRegistry] | None = None,
        # 中间件
        middlewares: Sequence[Middleware] | None = None,
        # 路由注册
        routers: Sequence[APIRouter | tuple[APIRouter, dict[str, Any]]] | None = None,
        route_registrars: Sequence[_RouteRegistrar] | None = None,
        # OpenAPI 自定义参数新增
        openapi_remove_422: bool = True,
        openapi_remove_validation_error: bool = True,
        # 异常处理器
        register_exceptions: bool = True,
        # 数据库集成（可选）
        engine_manager: EngineManager | None = None,
        session_factory: SessionFactory | None = None,
        # 健康检查
        health_check: bool = False,
        # 额外 FastAPI 参数
        **kwargs: Any,
) -> FastAPI:
    """创建并配置 FastAPI 应用实例

    工厂函数将以下组件统一装配到应用上：
        1. 生命周期管理 — 自动接入 :func:`fastapi_lifespan`，合并用户注册表与 core_registry
        2. 中间件 — 按列表顺序添加（先添加的在内层）
        3. 路由 — 支持直接传入 APIRouter 或 (router, kwargs) 元组
        4. 异常处理器 — 自动注册统一异常处理，返回标准 APIResponse 格式
        5. 数据库 — 可选地将 EngineManager / SessionFactory 挂载到 app.state

    装配完成后，``app.state`` 上可访问以下属性：
        - ``app.state.registries``  — 生命周期注册表列表
        - ``app.state.engine_manager`` — 数据库引擎管理器（若提供）
        - ``app.state.session_factory``  — 会话工厂（若提供）

    Example::

        from fastapi_augment.factory import create_app
        from fastapi_augment.lifespan import HookRegistry
        from fastapi_augment.db.sqlalchemy import EngineManager, SessionFactory, ClusterTopology, NodeConfig

        # 数据库
        topology = ClusterTopology(primary=NodeConfig(url='sqlite+aiosqlite:///app.db'))
        manager = EngineManager(topology).start()
        sessions = SessionFactory(manager)

        # 自定义钩子
        my_registry = HookRegistry()

        @my_registry.on_startup
        async def init_cache() -> None:
            ...

        app = create_app(
            title='My Service',
            registries=[my_registry],
            engine_manager=manager,
            session_factory=sessions,
        )

    Args:
        title: 应用标题
        summary: 应用摘要
        description: 应用描述
        version: 应用版本
        debug: 是否开启调试模式
        docs_url: Swagger UI 路径，None 禁用
        redoc_url: ReDoc 路径，None 禁用
        openapi_url: OpenAPI schema 路径，None 禁用
        cors_allow_origins: CORS 允许的源列表，None=不启用CORS
        cors_allow_methods: CORS 允许的 HTTP 方法列表，None=不启用CORS
        cors_allow_headers: CORS 允许的 HTTP 头列表，None=不启用CORS
        registries: 生命周期钩子注册表
        middlewares: Starlette 中间件列表
        routers: 路由列表，元素可以是 APIRouter 或 (router, kwargs) 元组
        route_registrars: 路由注册回调列表，接收 app 参数
        openapi_remove_422: 是否移除 422 验证错误响应
        openapi_remove_validation_error: 是否移除验证错误参数
        register_exceptions: 是否自动注册统一异常处理器，默认 True
        engine_manager: 数据库引擎管理器实例（可选）
        session_factory: 会话工厂实例（可选）
        health_check: 是否启用健康检查端点（默认 ``/health``）；
            当传入 ``engine_manager`` 时自动包含数据库连通性检查
        **kwargs: 传递给 FastAPI() 构造函数的额外参数（不允许传 lifespan）

    Returns:
        配置完成的 FastAPI 应用实例

    Raises:
        ValueError: 当 kwargs 中包含 lifespan 时抛出
    """
    # ---- 前置校验：禁止外部传入 lifespan ----
    if 'lifespan' in kwargs:
        raise ValueError(
            '不允许通过 kwargs 传递 lifespan，'
            '请使用 registries 参数注册生命周期钩子，工厂会自动管理 lifespan'
        )

    # ---- 1. 构建 FastAPI 实例 ----
    app = FastAPI(
        debug=debug,
        title=title,
        summary=summary,
        description=description,
        version=version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        middleware=middlewares,
        **kwargs,
    )

    # ---- 2. 添加 RequestId 中间件 ----
    app.add_middleware(RequestIdMiddleware)

    # ---- 3. CORS 配置 ----
    if cors_allow_origins:
        from fastapi.middleware.cors import CORSMiddleware

        opts = {
            'allow_origins': cors_allow_origins,
            'allow_credentials': '*' not in cors_allow_origins,
            'allow_methods': cors_allow_methods or ['*'],
            'allow_headers': cors_allow_headers or ['*']
        }
        app.add_middleware(CORSMiddleware, **opts)  # type: ignore

    # ---- 4. 生命周期注册表 ----
    resolved_registries = _resolve_registries(registries)
    app.state.registries = resolved_registries

    # 设置 lifespan（使用模块级的 fastapi_lifespan，它会自动将 core_registry 插入首位）
    app.router.lifespan_context = fastapi_lifespan

    # ---- 5. 路由 ----
    if routers:
        for item in routers:
            if isinstance(item, APIRouter):
                app.include_router(item)
            elif isinstance(item, tuple) and len(item) == 2:
                router, router_kwargs = item
                app.include_router(router, **router_kwargs)
            else:
                raise TypeError(
                    f'routers 元素必须为 APIRouter 或 (APIRouter, dict) 元组，'
                    f'实际为 {type(item).__name__}'
                )

    # ---- 6. 路由注册回调 ----
    if route_registrars:
        for registrar in route_registrars:
            registrar(app)

    # ---- 7. OpenAPI 配置 ----
    configure_openapi_schema(
        app,
        config=OpenAPICustomConfig(
            remove_422=openapi_remove_422,
            remove_validation_error_schema=openapi_remove_validation_error,
        )
    )

    # ---- 8. 异常处理器 ----
    if register_exceptions:
        register_exception_handlers(app)

    # ---- 9. 数据库组件挂载到 app.state ----
    if engine_manager is not None:
        app.state.engine_manager = engine_manager

    if session_factory is not None:
        app.state.session_factory = session_factory

    # ---- 10. 健康检查 ----
    if health_check:
        app.state.start_time = time()
        app.include_router(create_health_router(include_db_check=engine_manager is not None))

    return app


# -------------------------- 内部辅助 --------------------------

def _resolve_registries(
        registries: Sequence[HookRegistry] | HookRegistry | None,
) -> list[HookRegistry]:
    """将 registries 参数规范化为列表

    Args:
        registries: 用户传入的注册表参数，可以是单个 HookRegistry、
            HookRegistry 序列或 None

    Returns:
        规范化后的 HookRegistry 列表
    """
    if registries is None:
        return []

    if isinstance(registries, HookRegistry):
        return [registries]

    return list(registries)
