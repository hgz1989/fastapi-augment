"""
@Author         : hangu
@CreateDate     : 2026/8/31
@Description    : SQLAlchemy async engine factory, supporting single / master-replica / cluster topologies.
"""
from __future__ import annotations

import threading
from itertools import cycle
from typing import Any

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine
)

from .config import ClusterTopology, NodeConfig


# ── Engine Manager ───────────────────────────────────────────────────────────

class EngineManager:
    """
    Manages the full lifecycle of async SQLAlchemy engines.

    Usage::

        topology = ClusterTopology(
            primary=NodeConfig(url='postgresql+asyncpg://...'),
            replicas=[NodeConfig(url='postgresql+asyncpg://replica-1/...')],
        )
        manager = EngineManager(topology)
        manager.start()

        write_engine = manager.write_engine
        read_engine  = manager.next_read_engine()  # round-robin

        await manager.dispose()
    """

    def __init__(self, topology: ClusterTopology):
        self._topology = topology
        self._engines: dict[str, AsyncEngine] = {}
        self._write_key: str = 'primary'
        self._read_keys: list[str] = []
        self._read_cycle: cycle[str] | None = None
        self._disposed: bool = False
        self._lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> EngineManager:
        """Create all engines based on the topology. Returns *self* for chaining.

        幂等：已启动时直接返回自身，不会重建引擎导致旧连接池泄漏；
        需要重新构建拓扑时，先 ``dispose()`` 再 ``start()``

        Returns:
            The engine manager instance itself, for method chaining.
        """
        if self._engines:
            return self

        self._disposed = False
        self._engines[self._write_key] = self._create_engine(self._topology.primary)

        read_sources = self._topology.get_all_read_sources()
        for idx, node in enumerate(read_sources):
            key = f'read_{idx}'
            self._engines[key] = self._create_engine(node)
            self._read_keys.append(key)

        if self._read_keys:
            self._read_cycle = cycle(self._read_keys)

        return self

    async def dispose(self) -> None:
        """Dispose all engine connection pools gracefully.

        释放后再次访问引擎（write_engine / next_read_engine / get_engine）会抛出
        RuntimeError，避免裸 KeyError；``dispose()`` 后可再次 ``start()`` 重建
        """
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
            self._read_keys.clear()
            self._read_cycle = None
            self._disposed = True
        for engine in engines:
            await engine.dispose()

    # ── Engine Access ────────────────────────────────────────────────────

    def _ensure_active(self) -> None:
        """检查引擎管理器是否仍处于活动状态"""
        if self._disposed:
            raise RuntimeError('EngineManager 已 dispose，请先重新 start() 再访问引擎')

    @property
    def write_engine(self) -> AsyncEngine:
        """The primary engine used for all write operations.

        Returns:
            The primary async SQLAlchemy engine.

        Raises:
            RuntimeError: 管理器已 dispose 后访问
        """
        self._ensure_active()
        return self._engines[self._write_key]

    def next_read_engine(self) -> AsyncEngine:
        """Return the next read engine via round-robin; falls back to the write engine.

        Thread-safe: the round-robin iterator is protected by a lock.

        Returns:
            An async SQLAlchemy engine.

        Raises:
            RuntimeError: 管理器已 dispose 后访问
        """
        self._ensure_active()
        with self._lock:
            if self._read_cycle is not None:
                return self._engines[next(self._read_cycle)]
        return self.write_engine

    def get_engine(self, name: str) -> AsyncEngine:
        """Get a specific engine by its key (e.g. ``'primary'``, ``'read_0'``).

        Args:
            name: Engine key.

        Returns:
            An async SQLAlchemy engine.

        Raises:
            RuntimeError: 管理器已 dispose 后访问
            KeyError: If the engine key does not exist.
        """
        self._ensure_active()
        engine = self._engines.get(name)
        if engine is None:
            available = ', '.join(sorted(self._engines)) or '(none)'
            raise KeyError(f'Engine {name!r} not found; available engines: {available}')
        return engine

    @property
    def engines(self) -> dict[str, AsyncEngine]:
        """All engines managed by the engine manager.

        Returns:
            A dictionary of engine key -> async SQLAlchemy engine.
        """
        return dict(self._engines)

    @property
    def topology(self) -> ClusterTopology:
        """The database topology configuration.

        Returns:
            A ClusterTopology instance.
        """
        return self._topology

    # ── Internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _create_engine(node: NodeConfig) -> AsyncEngine:
        """Create an async SQLAlchemy engine based on the given node configuration.

        SQLite 使用 NullPool，不接受 QueuePool 参数（pool_size 等），
        因此对 SQLite 节点只传 echo / connect_args。

        Args:
            node: Database node configuration.

        Returns:
            An async SQLAlchemy engine.
        """
        kwargs: dict[str, Any] = {
            'echo': node.echo,
            'connect_args': node.connect_args,
        }
        if 'sqlite' not in (node.url or '').split('+', 1)[0].lower():
            if not node.pool_enabled:
                kwargs['poolclass'] = NullPool
            else:
                kwargs.update(
                    pool_size=node.pool_size,
                    max_overflow=node.max_overflow,
                    pool_timeout=node.pool_timeout,
                    pool_recycle=node.pool_recycle,
                    pool_pre_ping=node.pool_pre_ping,
                )
        return create_async_engine(node.url, **kwargs)
