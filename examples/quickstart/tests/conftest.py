"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 测试 fixture——临时文件 SQLite 引擎 + 会话工厂 + 应用实例（与落盘配置隔离）
"""
import pytest_asyncio
from fastapi_augment import create_app
from fastapi_augment.db.sqlalchemy import (
    ClusterTopology,
    EngineManager,
    ModelBase,
    NodeConfig,
    SessionFactory,
)
from httpx import ASGITransport, AsyncClient

from apps.api.router import build_router
from config import project_settings


@pytest_asyncio.fixture()
async def engine_manager(tmp_path) -> EngineManager:
    """临时文件 SQLite 引擎（覆盖默认落盘配置，测试数据不落盘）

    使用文件库而非 ``sqlite+aiosqlite://`` 内存库：内存库每个连接独立，
    读写分离的两个会话会看到不同的数据库；文件库由所有连接共享。
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"  # tmp_path 为 Path，直接拼 URL（Windows 斜杠由 SQLAlchemy 处理）
    topology = ClusterTopology(primary=NodeConfig(url=db_url))
    manager = EngineManager(topology).start()
    async with manager.write_engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
    yield manager
    await manager.dispose()


@pytest_asyncio.fixture()
async def sessions(engine_manager: EngineManager) -> SessionFactory:
    """会话工厂（绑定内存引擎）"""
    factory = SessionFactory(engine_manager)
    yield factory
    await factory.dispose()


@pytest_asyncio.fixture()
async def client(sessions: SessionFactory, engine_manager: EngineManager):
    """基于内存库重建的应用实例（每个测试独立数据）"""
    test_app = create_app(
        title=project_settings.title,
        version=project_settings.version,
        health_check=True,
        engine_manager=engine_manager,
        session_factory=sessions,
        routers=[build_router(sessions)],
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url='http://test') as c:
        yield c
