"""
db.sqlalchemy.session 模块测试 — SessionFactory
db.sqlalchemy.model_base 模块测试 — ModelBase / ULID 生成
db.sqlalchemy.mixins 模块测试 — 各混入类
"""

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_augment.db.sqlalchemy.engine import (
    ClusterTopology,
    NodeConfig,
    EngineManager
)
from fastapi_augment.db.sqlalchemy.mixins.audit import (
    CreatedByMixin,
    UpdatedByMixin,
    AuditMixin
)
from fastapi_augment.db.sqlalchemy.mixins.soft_delete import (
    SoftDeleteMixin,
    SoftDeleteAuditMixin
)
from fastapi_augment.db.sqlalchemy.mixins.timestamp import (
    TimestampMixin,
    CreatedAtMixin
)
from fastapi_augment.db.sqlalchemy.model_base import (
    ModelBase,
    _generate_ulid
)
from fastapi_augment.db.sqlalchemy.session import (
    SessionFactory
)


# ── 测试模型 ──────────────────────────────────────────────────────────

class SampleModel(TimestampMixin, ModelBase):
    __tablename__ = 'sample_models'
    name: Mapped[str] = mapped_column(String(100))


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def engine_manager(tmp_path):
    db_file = tmp_path / 'test_session.db'
    topology = ClusterTopology(
        primary=NodeConfig(url=f'sqlite+aiosqlite:///{db_file}')
    )
    manager = EngineManager(topology).start()
    async with manager.write_engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
    yield manager
    # dispose 后引擎已清空，需判断是否还有引擎可用
    if manager.engines:
        async with manager.write_engine.begin() as conn:
            await conn.run_sync(ModelBase.metadata.drop_all)
        await manager.dispose()


@pytest_asyncio.fixture()
async def session_factory(engine_manager: EngineManager):
    return SessionFactory(engine_manager)


# ── SessionFactory ────────────────────────────────────────────────────

class TestSessionFactory:

    def test_engine_manager_property(self, engine_manager, session_factory):
        assert session_factory.engine_manager is engine_manager

    async def test_write_session(self, session_factory: SessionFactory):
        async with session_factory.write_session() as session:
            assert isinstance(session, AsyncSession)
            item = SampleModel(name='test')
            session.add(item)
            await session.flush()
            assert item.id is not None

    async def test_read_session(self, session_factory: SessionFactory):
        # 先写入数据
        async with session_factory.write_session() as session:
            session.add(SampleModel(name='readable'))
            await session.commit()

        # 读取
        async with session_factory.read_session() as session:
            result = await session.execute(select(SampleModel))
            items = result.scalars().all()
            assert len(items) == 1
            assert items[0].name == 'readable'

    async def test_transaction_commit(self, session_factory: SessionFactory):
        async with session_factory.transaction() as session:
            session.add(SampleModel(name='committed'))

        # 验证数据已提交
        async with session_factory.read_session() as session:
            result = await session.execute(select(SampleModel))
            assert len(result.scalars().all()) == 1

    async def test_transaction_rollback(self, session_factory: SessionFactory):
        try:
            async with session_factory.transaction() as session:
                session.add(SampleModel(name='will_rollback'))
                # 测试刻意在事务上下文内抛错以验证回滚
                raise ValueError('force rollback')  # noqa: TRY301
        except ValueError:
            pass

        # 验证数据已回滚
        async with session_factory.read_session() as session:
            result = await session.execute(select(SampleModel))
            assert len(result.scalars().all()) == 0

    async def test_depends_write(self, session_factory: SessionFactory):
        async for session in session_factory.depends_write():
            assert isinstance(session, AsyncSession)
            break

    async def test_depends_read(self, session_factory: SessionFactory):
        async for session in session_factory.depends_read():
            assert isinstance(session, AsyncSession)
            break

    async def test_dispose(self, engine_manager):
        factory = SessionFactory(engine_manager)
        await factory.dispose()
        assert len(engine_manager.engines) == 0


# ── ModelBase / ULID ──────────────────────────────────────────────────

class TestModelBase:

    def test_generate_ulid_format(self):
        ulid = _generate_ulid()
        assert len(ulid) == 26
        assert ulid == ulid.lower()

    def test_generate_ulid_unique(self):
        ulids = {_generate_ulid() for _ in range(100)}
        assert len(ulids) == 100

    def test_model_base_is_abstract(self):
        assert ModelBase.__abstract__ is True


# ── Mixins 列定义验证 ─────────────────────────────────────────────────

class TestMixins:

    def test_created_at_mixin_has_column(self):
        assert hasattr(CreatedAtMixin, 'created_at')

    def test_timestamp_mixin_has_both_columns(self):
        assert hasattr(TimestampMixin, 'created_at')
        assert hasattr(TimestampMixin, 'updated_at')

    def test_soft_delete_mixin_has_columns(self):
        assert hasattr(SoftDeleteMixin, 'is_deleted')
        assert hasattr(SoftDeleteMixin, 'deleted_at')

    def test_soft_delete_mixin_not_deleted_expr(self):
        expr = SoftDeleteMixin.not_deleted()
        assert expr is not None

    def test_soft_delete_mixin_only_deleted_expr(self):
        expr = SoftDeleteMixin.only_deleted()
        assert expr is not None

    def test_soft_delete_audit_mixin_has_deleted_by(self):
        assert hasattr(SoftDeleteAuditMixin, 'deleted_by')
        # 继承自 SoftDeleteMixin
        assert hasattr(SoftDeleteAuditMixin, 'is_deleted')

    def test_created_by_mixin_has_column(self):
        assert hasattr(CreatedByMixin, 'created_by')

    def test_updated_by_mixin_has_column(self):
        assert hasattr(UpdatedByMixin, 'updated_by')

    def test_audit_mixin_combines_both(self):
        assert hasattr(AuditMixin, 'created_by')
        assert hasattr(AuditMixin, 'updated_by')

    def test_sample_model_has_all_columns(self):
        """SampleModel 继承了 TimestampMixin + ModelBase，验证列都存在"""
        assert hasattr(SampleModel, 'id')
        assert hasattr(SampleModel, 'name')
        assert hasattr(SampleModel, 'created_at')
        assert hasattr(SampleModel, 'updated_at')
