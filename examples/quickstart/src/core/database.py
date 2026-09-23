"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 数据库装配——拓扑 → 引擎 → 会话工厂
"""
from fastapi_augment.db.sqlalchemy import (
    ClusterTopology,
    EngineManager,
    NodeConfig,
    SessionFactory,
)

from config import settings


def build_database() -> tuple[EngineManager, SessionFactory]:
    """组装数据库：单库拓扑 + 引擎管理 + 会话工厂

    拓扑支持单库 / 主从 / 集群（详见库文档「数据库层 — EngineManager」）；
    示例使用单库，读写会话默认都走主引擎。

    Returns:
        (engine_manager, session_factory) 二元组
    """
    topology = ClusterTopology(
        primary=NodeConfig(url=settings.database.url),
    )
    manager = EngineManager(topology).start()
    sessions = SessionFactory(manager)
    return manager, sessions
