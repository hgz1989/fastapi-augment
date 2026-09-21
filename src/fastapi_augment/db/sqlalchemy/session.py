"""
@Author         : hangu
@CreateDate     : 2026/8/31
@Description    : Async session factory with read/write splitting, built on top of EngineManager.
"""
from __future__ import annotations

import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncEngine,
    AsyncSession
)

from .engine import EngineManager


class SessionFactory:
    """
    Async session factory that transparently routes reads and writes
    to the correct database engine.

    Usage::

        manager = EngineManager(topology).start()
        factory = SessionFactory(manager)

        # Write session (always hits primary)
        async with factory.write_session() as session:
            session.add(User(name='alice'))
            await session.commit()

        # Read session (round-robin across replicas)
        async with factory.read_session() as session:
            result = await session.execute(select(User))

        # FastAPI dependencies
        @app.get('/users')
        async def list_users(session: AsyncSession = Depends(factory.depends_read)):
            pass
    """

    def __init__(
            self,
            engine_manager: EngineManager,
            *,
            expire_on_commit: bool = False,
            session_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._manager = engine_manager
        self._session_kwargs = session_kwargs or {}
        self._expire_on_commit = expire_on_commit

        self._write_factory = async_sessionmaker(
            bind=engine_manager.write_engine,
            class_=AsyncSession,
            expire_on_commit=expire_on_commit,
            **self._session_kwargs,
        )

        # 缓存读引擎对应的 session factory，避免每次 read_session 重复创建
        self._read_factories: WeakKeyDictionary[AsyncEngine, async_sessionmaker[AsyncSession]] = WeakKeyDictionary()
        self._lock = threading.Lock()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def engine_manager(self) -> EngineManager:
        """The underlying engine manager.

        Returns:
            The engine manager.
        """

        return self._manager

    # ── Session Factories (async context managers) ───────────────────────

    @asynccontextmanager
    async def write_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a session bound to the **primary** (write) engine

        Returns:
            An async session bound to the primary engine.
        """
        async with self._write_factory() as session:
            yield session

    @asynccontextmanager
    async def read_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a session bound to a **read** engine (round-robin across replicas).

        Per-engine ``async_sessionmaker`` instances are cached to avoid
        redundant factory creation.  The cache is thread-safe.

        Returns:
            An async session bound to a read engine.
        """
        read_engine = self._manager.next_read_engine()

        with self._lock:
            factory = self._read_factories.get(read_engine)
            if factory is None:
                # 先查缓存再创建，避免 setdefault 在命中缓存时仍白建 factory
                factory = async_sessionmaker(
                    bind=read_engine,
                    class_=AsyncSession,
                    expire_on_commit=self._expire_on_commit,
                    **self._session_kwargs,
                )
                self._read_factories[read_engine] = factory

        async with factory() as session:
            yield session

    # ── Transactional helpers ────────────────────────────────────────────

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """Write session with automatic commit / rollback.

        Commits on clean exit, rolls back on any exception::

            async with factory.transaction() as session:
                session.add(obj)
                # auto-commit here

        Returns:
            An async session bound to the primary engine.
        """
        async with self.write_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ── FastAPI Dependencies ─────────────────────────────────────────────

    async def depends_write(self) -> AsyncGenerator[AsyncSession, None]:
        """FastAPI ``Depends()`` — inject a write session.

        Returns:
            An async session bound to the primary engine.
        """
        async with self.write_session() as session:
            yield session

    async def depends_read(self) -> AsyncGenerator[AsyncSession, None]:
        """FastAPI ``Depends()`` — inject a read session.

        Returns:
            An async session bound to a read engine.
        """
        async with self.read_session() as session:
            yield session

    async def depends_transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """FastAPI ``Depends()`` — inject a transaction.

        Returns:
            An async session bound to the primary engine.
        """
        async with self.transaction() as session:
            yield session

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def dispose(self) -> None:
        """Dispose the underlying engine manager and all connection pools."""
        await self._manager.dispose()

    def __repr__(self) -> str:
        engines = list(self._read_factories.keys())
        return (
            f'SessionFactory(write_engine={self._manager.write_engine.url!s}, '
            f'read_engines={[str(e.url) for e in engines]})'
        )
