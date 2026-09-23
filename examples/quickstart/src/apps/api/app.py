"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : FastAPI 应用装配（组合根）——数据库、生命周期、路由
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi_augment import create_app
from fastapi_augment.db.sqlalchemy import ModelBase
from fastapi_augment.lifespan import HookRegistry
from fastapi_augment.schemas import response_fail
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.router import build_router
from config import project_settings, root_dir
from core.database import build_database

# ── 数据库 ─────────────────────────────────────────────────
engine_manager, session_factory = build_database()

# ── 生命周期：启动建表，关闭释放连接池 ──────────────────────
registry = HookRegistry()


@registry.on_startup(priority=100)
async def _init_schema(_app: FastAPI) -> None:
    """启动时建表（SQLite 首次运行自动创建 data/ 目录）"""
    (root_dir / 'data').mkdir(parents=True, exist_ok=True)
    async with engine_manager.write_engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)


@registry.on_shutdown
async def _dispose(_app: FastAPI) -> None:
    """关闭时释放数据库连接池"""
    await session_factory.dispose()


# ── 应用装配 ───────────────────────────────────────────────
app = create_app(
    title=project_settings.title,
    summary=project_settings.summary,
    version=project_settings.version,
    debug=project_settings.debug,
    health_check=True,
    registries=[registry],
    engine_manager=engine_manager,
    session_factory=session_factory,
    routers=[build_router(session_factory)],
)


# ── HTTP 异常统一为 APIResponse 格式 ────────────────────────
# 业务代码抛出的 4xx 异常（如 NotFoundError）默认返回 FastAPI 的
# {"detail": ...} 格式；此处显式转为统一响应，与正常接口一致。
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
) -> JSONResponse:
    """HTTP 异常 → 统一 APIResponse 格式"""
    body = response_fail(code=exc.status_code, message=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(mode='json', by_alias=True),
    )
