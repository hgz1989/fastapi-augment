"""
db.sqlalchemy.model_base 模块测试 — ModelBase ULID 主键与基础行为
"""
import pytest_asyncio
from sqlalchemy import String
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_augment.db.sqlalchemy.model_base import (
    ModelBase,
    _generate_ulid
)


# ── 测试模型 ──────────────────────────────────────────────────────────

class SampleModel(ModelBase):
    """测试用模型"""
    __tablename__ = 'test_model_base_samples'
    name: Mapped[str] = mapped_column(String(100), comment='名称')


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def session():
    eng = create_async_engine('sqlite+aiosqlite://', echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
    factory = async_sessionmaker(bind=eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    async with eng.begin() as conn:
        await conn.run_sync(ModelBase.metadata.drop_all)
    await eng.dispose()


# ── Tests ─────────────────────────────────────────────────────────────

class TestGenerateUlid:

    def test_returns_string(self):
        result = _generate_ulid()
        assert isinstance(result, str)

    def test_length_26(self):
        assert len(_generate_ulid()) == 26

    def test_lowercase(self):
        ulid = _generate_ulid()
        assert ulid == ulid.lower()

    def test_unique(self):
        ids = {_generate_ulid() for _ in range(100)}
        assert len(ids) == 100


class TestModelBase:

    def test_is_abstract(self):
        assert ModelBase.__abstract__ is True

    async def test_auto_id_on_flush(self, session: AsyncSession):
        obj = SampleModel(name='test')
        session.add(obj)
        await session.flush()
        assert obj.id is not None
        assert len(obj.id) == 26

    async def test_id_is_ulid_format(self, session: AsyncSession):
        obj = SampleModel(name='test')
        session.add(obj)
        await session.flush()
        # ULID: 26 chars, lowercase alphanumeric
        assert obj.id.isalnum()
        assert obj.id == obj.id.lower()

    async def test_multiple_instances_get_unique_ids(self, session: AsyncSession):
        a = SampleModel(name='a')
        b = SampleModel(name='b')
        session.add_all([a, b])
        await session.flush()
        assert a.id != b.id

    def test_id_column_is_primary_key(self):
        col = SampleModel.__table__.columns['id']
        assert col.primary_key is True

    def test_id_column_type_is_string_26(self):
        col = SampleModel.__table__.columns['id']
        assert col.type.length == 26
