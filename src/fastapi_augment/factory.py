"""
@Author         : hangu
@CreateDate     : 2026/9/3
@Description    : FastAPI 应用工厂
                  - 统一创建 FastAPI 实例并自动装配生命周期、数据库、中间件、路由
                  - 支持可选的 SQLAlchemy 读写分离集成
                  - 通过 app.state 暴露核心组件供业务层使用
"""
from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
from collections.abc import Callable, Sequence
from importlib import metadata as _importlib_metadata
from logging import getLogger
from pathlib import Path
from time import sleep, time
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, APIRouter
from starlette.middleware import Middleware

from .common.exception_handlers import (
    register_exception_handlers
)
from .common.utils.resources import (
    file_data_uri,
    package_asset_data_uri
)
from .health import create_health_router
from .lifespan import (
    fastapi_lifespan,
    HookRegistry
)
from .middlewares import (
    RequestIdMiddleware,
    DocsAuthMiddleware
)
from .openapi import (
    configure_openapi_schema,
    OpenAPICustomConfig
)

if TYPE_CHECKING:
    from .db.sqlalchemy import EngineManager, SessionFactory

_logger = getLogger(__name__)

# -------------------------- 类型别名 --------------------------
# 路由注册回调：接收 app 实例，负责 include_router 等操作
_RouteRegistrar = Callable[[FastAPI], None]


def _default_app_version() -> str:
    """返回包当前版本号（单一事实源：发行元数据）

    Returns:
        已安装发行版的版本号；源码直接运行（未安装）时回退 ``0.0.0``
    """
    try:
        return _importlib_metadata.version('fastapi-augment')
    except _importlib_metadata.PackageNotFoundError:
        return '0.0.0'


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
        version: str | None = None,
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
        # Docs 文档保护：登录页 + 签名 Cookie（配置后 /docs /redoc /openapi.json 需登录）
        # 格式 [{"username": "admin", "password": "xxx"}, ...]，None 不保护
        docs_credentials: list[dict[str, str]] | None = None,
        # Docs 保护签名密钥（HMAC-SHA256）：显式传入优先，否则回退环境变量
        # DOCS_AUTH_SECRET，再否则随机生成并经临时文件在同机多进程间共享
        # （多主机部署需配置 DOCS_AUTH_SECRET，否则跨机 Cookie 失效）
        docs_auth_secret: str | None = None,
        # Docs logo：URL / data URI / 本地路径均可；None 时尝试包内 assets/logo.png
        # （存在则自动注入 ReDoc info.x-logo 与 docs 登录页，Swagger 不支持换 logo）
        docs_logo: str | Path | None = None,
        # Docs 登录 Cookie 有效期（秒）；默认 None 表示会话级 Cookie，
        # 关闭浏览器即失效（服务端 token 有效期仍按默认 2 小时兜底）
        docs_max_age: int | None = None,
        # Docs 登录 Cookie 是否仅 HTTPS 传输；生产环境部署 HTTPS 后建议开启
        docs_cookie_secure: bool = False,
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
        version: 应用版本；不传时自动取当前包版本号（发行元数据单一事实源）
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
        docs_credentials: Docs 文档访问保护（登录页 + 签名 Cookie），格式
            [{"username": "admin", "password": "xxx"}, ...]，支持多账号；配置后
            /docs /redoc /openapi.json 未登录会重定向到对应当前路径的登录页
            （如 /docs/login?next=/docs）；None 时回退读取环境变量：
            DOCS_CREDENTIALS（多账号，格式 user1:pass1,user2:pass2）优先，
            否则 DOCS_USERNAME / DOCS_PASSWORD（单账号，兼容），均未设置则不保护
        docs_auth_secret: Docs 登录 Cookie 签名密钥（HMAC-SHA256）。显式传入
            优先，否则回退环境变量 DOCS_AUTH_SECRET，再否则随机生成并通过
            临时文件在同机多进程间共享（uvicorn/gunicorn 多 worker 部署下
            各进程共享同一密钥；多主机部署无法跨机共享，需配置该环境变量）；
            生产环境建议配置随机长密钥
        docs_logo: Docs 页面 logo。支持 URL（``http(s)://``）、``data:`` URI 或
            本地文件路径（自动转为 data URI 内联）；None 时尝试包内
            ``fastapi_augment/assets/logo.png``（存在则生效）。注入位置：
            ReDoc 顶部（OpenAPI ``info.x-logo`` 扩展）与 docs 登录页；
            Swagger UI 不支持更换 logo（FastAPI 无此参数，且不自建 docs 路由）
        docs_max_age: Docs 登录 Cookie 有效期（秒），默认 None 表示
            会话级 Cookie，**关闭浏览器即失效**（服务端 token 有效期仍按默认
            2 小时兜底校验，防复制滥用）
        docs_cookie_secure: Docs 登录 Cookie 是否仅 HTTPS 传输；生产环境部署
            HTTPS 后建议开启
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
    # 原生 docs/redoc/openapi 路由保留，文档访问认证由 DocsAuthMiddleware 中间件拦截
    if version is None:
        version = _default_app_version()
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
        app.add_middleware(CORSMiddleware, **opts)  # type: ignore[arg-type]

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
    # docs logo：显式传入或包内 assets/logo.png（存在时生效），供 ReDoc 与登录页使用
    _docs_logo = _resolve_docs_logo(docs_logo)
    configure_openapi_schema(
        app,
        config=OpenAPICustomConfig(
            remove_422=openapi_remove_422,
            remove_validation_error_schema=openapi_remove_validation_error,
            logo=_docs_logo,
            logo_alt_text=app.title,
        )
    )

    # ---- 7.5 Docs 文档保护：登录页 + 签名 Cookie 中间件 ----
    # 凭证优先取显式传入的 docs_credentials，否则回退环境变量
    # （DOCS_CREDENTIALS 多账号优先，其次 DOCS_USERNAME/DOCS_PASSWORD 单账号兼容）
    _docs_credentials = _resolve_docs_credentials(docs_credentials)
    # 受保护路径 = 实际启用的 docs/redoc/openapi 路径（支持自定义，禁用项自动排除）
    _docs_protected_paths = [path for path in (docs_url, redoc_url, openapi_url) if path]
    if _docs_credentials and _docs_protected_paths:
        # 随机密钥共享文件按 标题+凭证 哈希命名，隔离同机不同应用
        _docs_secret = _resolve_docs_secret(
            docs_auth_secret, cache_key=f'{app.title}:{_docs_credentials}'
        )
        # Starlette _MiddlewareFactory 协议要求 __call__(app, ...) -> ASGIApp，
        # 与 ASGI 中间件实际 __call__(scope, receive, send) 的固有签名张力（同 CORS）
        opts = {
            'credentials': _docs_credentials,
            'secret': _docs_secret,
            'protected_paths': _docs_protected_paths,
            'title': app.title,
            'summary': app.summary,
            'logo': _docs_logo,
            'max_age': docs_max_age,
            'cookie_secure': docs_cookie_secure,
        }
        app.add_middleware(DocsAuthMiddleware, **opts)  # type: ignore[arg-type]

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

def _resolve_docs_credentials(
        docs_credentials: list[dict[str, str]] | None,
) -> list[dict[str, str]] | None:
    """解析 Docs 访问保护凭证：优先显式传入，否则回退到环境变量

    环境变量解析顺序：
      1. ``DOCS_CREDENTIALS``：多账号，格式 ``user1:pass1,user2:pass2``
      2. ``DOCS_USERNAME`` + ``DOCS_PASSWORD``：单账号（兼容，优先级低于前者）
    显式传入的 ``docs_credentials`` 支持多账号。

    Args:
        docs_credentials: 显式传入的账号密码列表；None 表示尝试从环境变量读取

    Returns:
        凭证列表；未配置任何凭证时返回 None（不启用保护）
    """
    if docs_credentials is not None:
        return docs_credentials

    multi = os.getenv('DOCS_CREDENTIALS')
    if multi:
        return _parse_credentials(multi)

    username = os.getenv('DOCS_USERNAME')
    password = os.getenv('DOCS_PASSWORD')
    if username and password:
        return [{'username': username, 'password': password}]
    return None


def _parse_credentials(raw: str) -> list[dict[str, str]]:
    """解析 ``user1:pass1,user2:pass2`` 格式的凭证字符串为列表

    每个账号用冒号分隔用户名与密码（按第一个冒号切分，密码可含冒号）；
    多账号之间用逗号分隔（约定密码不含逗号）；空白项与缺字段项自动忽略。

    Args:
        raw: 原始凭证字符串

    Returns:
        凭证列表
    """
    result: list[dict[str, str]] = []
    for item in raw.split(','):
        item = item.strip()
        if not item:
            continue
        username, _, password = item.partition(':')
        username = username.strip()
        password = password.strip()
        if username and password:
            result.append({'username': username, 'password': password})
    return result


def _resolve_docs_secret(
        docs_auth_secret: str | None = None,
        *,
        cache_key: str = '',
) -> str:
    """解析 Docs 登录 Cookie 签名密钥：显式传入 → 环境变量 → 随机生成

    密钥用于 HMAC-SHA256 签名登录 Cookie；未配置时生成随机密钥并通过
    临时文件在同机多进程间共享（见 :func:`_shared_random_secret`），
    避免 uvicorn/gunicorn 多 worker 部署时各进程密钥互不相同导致
    Cookie 校验失败。

    Args:
        docs_auth_secret: 显式传入的签名密钥；None 表示尝试环境变量
        cache_key: 随机密钥共享文件的命名键（应用标题 + 凭证），
            用于隔离同机不同应用的密钥文件

    Returns:
        签名密钥
    """
    if docs_auth_secret:
        return docs_auth_secret

    env_secret = os.getenv('DOCS_AUTH_SECRET')
    if env_secret:
        return env_secret
    return _shared_random_secret(cache_key)


# 并发创建竞态下等待对方写入的轮询参数（共 1 秒）
_SECRET_READ_INTERVAL = 0.05
_SECRET_READ_ATTEMPTS = 20


def _shared_random_secret(cache_key: str) -> str:
    """生成随机密钥并以临时文件在同机多进程间共享

    多 worker 部署下每个进程独立调用 ``create_app``，若各自随机生成
    密钥，Cookie 签名互不认可（表现为间歇性跳回登录页）。首个进程以
    ``O_CREAT | O_EXCL`` 原子创建文件并写入密钥，后续进程读取同一
    文件；文件按 ``cache_key``（应用标题 + 凭证）哈希命名，防止同机
    不同应用互相认可 Cookie。本地文件无法跨主机共享，多主机部署仍
    需配置 ``DOCS_AUTH_SECRET``。

    Args:
        cache_key: 共享文件命名键

    Returns:
        共享随机密钥；临时目录不可写时退化为进程内随机密钥
    """
    _logger.warning(
        'DOCS_AUTH_SECRET 未配置，Docs 登录密钥随机生成并通过临时文件共享；'
        '生产环境（尤其多主机部署）请显式配置 DOCS_AUTH_SECRET'
    )
    digest = hashlib.sha256(cache_key.encode('utf-8')).hexdigest()[:16]
    path = Path(tempfile.gettempdir()) / f'fastapi-augment-docs-secret-{digest}'

    existing = _read_secret_file(path)
    if existing is not None:
        return existing

    secret = secrets.token_hex(32)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # 竞争失败的进程读取创建方写入的密钥；创建与写入之间存在
        # 微秒级窗口，短暂轮询等待（超时则退化为各自的随机密钥）
        for _ in range(_SECRET_READ_ATTEMPTS):
            existing = _read_secret_file(path)
            if existing is not None:
                return existing
            sleep(_SECRET_READ_INTERVAL)
        return secret
    except OSError:
        return secret
    try:
        os.write(fd, secret.encode('ascii'))
    finally:
        os.close(fd)
    return secret


def _read_secret_file(path: Path) -> str | None:
    """读取共享密钥文件并校验格式（token_hex(32) 的 64 位十六进制）"""
    try:
        content = path.read_text(encoding='ascii').strip()
    except (OSError, UnicodeDecodeError):
        return None
    if len(content) != 64:
        return None
    try:
        int(content, 16)
    except ValueError:
        return None
    return content


def _resolve_docs_logo(docs_logo: str | Path | None) -> str | None:
    """解析 Docs logo：显式传入 → 包内 assets/logo.png 默认资源

    传入 ``data:`` URI 或 ``http(s)://`` URL 时直接使用；
    传入本地路径读取为 data URI；None 时尝试包内 ``assets/logo.png``，
    文件不存在则返回 None（不注入 logo，行为与旧版一致）。

    Args:
        docs_logo: 显式传入的 logo（URL / data URI / 本地路径）；None 尝试默认资源

    Returns:
        logo 的 data URI 或 URL；不可用时返回 None
    """
    if docs_logo is None:
        return package_asset_data_uri('logo.png')
    if isinstance(docs_logo, Path):
        return file_data_uri(docs_logo)
    if docs_logo.startswith(('data:', 'http://', 'https://')):
        return docs_logo
    return file_data_uri(Path(docs_logo))


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
