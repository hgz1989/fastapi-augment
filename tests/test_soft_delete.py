"""
RepositoryBase 软删除收尾与聚合能力测试

覆盖：
- 软删模型查询默认过滤已删除行，include_deleted=True 可放开
- delete 系列自动转软删，hard_delete_* 显式物理删除
- 聚合 sum/avg/min/max 与软删联动
- update_where 批量更新
- 非软删模型行为保持不变（回归）
"""
import pytest
import pytest_asyncio
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_augment.db.sqlalchemy.mixins.soft_delete import (
    SoftDeleteMixin
)
from fastapi_augment.db.sqlalchemy.mixins.timestamp import (
    TimestampMixin
)
from fastapi_augment.db.sqlalchemy.model_base import (
    ModelBase
)
from fastapi_augment.db.sqlalchemy.repository_base import (
    RepositoryBase
)


# ── 测试模型 ──────────────────────────────────────────────────────────

class SoftDeleteItem(TimestampMixin, SoftDeleteMixin, ModelBase):
    """软删测试模型"""
    __tablename__ = 'soft_delete_items'

    name: Mapped[str] = mapped_column(String(100), comment='名称')
    role: Mapped[str] = mapped_column(String(50), default='user', comment='角色')
    amount: Mapped[int] = mapped_column(Integer, default=0, comment='金额')


class PlainItem(ModelBase):
    """非软删测试模型（回归用）"""
    __tablename__ = 'plain_items'

    name: Mapped[str] = mapped_column(String(100), comment='名称')


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def engine():
    """创建内存 SQLite 异步引擎"""
    eng = create_async_engine('sqlite+aiosqlite://', echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(ModelBase.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture()
async def session(engine):
    """创建异步 session"""
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.fixture()
def repo() -> RepositoryBase[SoftDeleteItem]:
    return RepositoryBase(SoftDeleteItem)


@pytest.fixture()
def plain_repo() -> RepositoryBase[PlainItem]:
    return RepositoryBase(PlainItem)


async def _make_items(session: AsyncSession, *names: str) -> list[SoftDeleteItem]:
    """批量创建 UserItem 并返回实例列表"""
    items = [SoftDeleteItem(name=name, amount=i * 10) for i, name in enumerate(names)]
    await RepositoryBase.create_many(session, items)
    return items


async def _soft_delete(session: AsyncSession, item: SoftDeleteItem) -> None:
    """直接软删一个实例（模拟旧版 service 层写法）"""
    await RepositoryBase.delete(session, item)


# ── 查询默认过滤 ──────────────────────────────────────────────────────

class TestSoftDeleteFiltering:

    async def test_get_excludes_deleted(self, session: AsyncSession, repo):
        """get 默认不返回已软删行"""
        items = await _make_items(session, 'alice')
        item = items[0]
        await _soft_delete(session, item)
        assert await repo.get(session, item.id) is None

    async def test_get_include_deleted(self, session: AsyncSession, repo):
        """include_deleted=True 返回已软删行"""
        item = (await _make_items(session, 'alice'))[0]
        await _soft_delete(session, item)
        fetched = await repo.get(session, item.id, include_deleted=True)
        assert fetched is not None
        assert fetched.is_deleted is True

    async def test_list_excludes_deleted(self, session: AsyncSession, repo):
        """list 默认排除已软删行"""
        items = await _make_items(session, 'a', 'b', 'c')
        await _soft_delete(session, items[1])
        assert [i.name for i in await repo.list(session)] == ['a', 'c']

    async def test_list_include_deleted(self, session: AsyncSession, repo):
        """list include_deleted=True 返回全部"""
        items = await _make_items(session, 'a', 'b')
        await _soft_delete(session, items[0])
        assert len(await repo.list(session, include_deleted=True)) == 2

    async def test_count_excludes_deleted(self, session: AsyncSession, repo):
        """count 默认排除已软删行"""
        items = await _make_items(session, 'a', 'b', 'c')
        await _soft_delete(session, items[0])
        assert await repo.count(session) == 2
        assert await repo.count(session, include_deleted=True) == 3

    async def test_exists_excludes_deleted(self, session: AsyncSession, repo):
        """exists 默认认为已软删行不存在"""
        item = (await _make_items(session, 'a'))[0]
        await _soft_delete(session, item)
        assert await repo.exists(session, name='a') is False
        assert await repo.exists(session, name='a', include_deleted=True) is True

    async def test_get_first_excludes_deleted(self, session: AsyncSession, repo):
        """get_first 默认排除已软删行"""
        items = await _make_items(session, 'a', 'b')
        await _soft_delete(session, items[0])
        assert await repo.get_first(session, name='a') is None

    async def test_get_unique_excludes_deleted(self, session: AsyncSession, repo):
        """get_unique 默认排除已软删行"""
        items = await _make_items(session, 'a', 'b')
        await _soft_delete(session, items[0])
        assert await repo.get_unique(session, name='a') is None

    async def test_paginate_excludes_deleted(self, session: AsyncSession, repo):
        """paginate 默认排除已软删行，include_deleted 放开"""
        items = await _make_items(session, 'a', 'b', 'c')
        await _soft_delete(session, items[1])
        result = await repo.paginate(session, page=1, size=10)
        assert result['total'] == 2
        assert [i.name for i in result['items']] == ['a', 'c']
        result_all = await repo.paginate(session, page=1, size=10, include_deleted=True)
        assert result_all['total'] == 3


# ── 删除自动转软删 ─────────────────────────────────────────────────────

class TestSoftDeleteDelete:

    async def test_delete_by_id_soft_deletes(self, session: AsyncSession, repo):
        """delete_by_id 转软删：默认不可见，include_deleted 可见且带标记"""
        item = (await _make_items(session, 'bob'))[0]
        assert await repo.delete_by_id(session, item.id) is True
        assert await repo.get(session, item.id) is None
        deleted = await repo.get(session, item.id, include_deleted=True)
        assert deleted is not None
        assert deleted.is_deleted is True
        assert deleted.deleted_at is not None

    async def test_delete_by_id_twice_returns_false(self, session: AsyncSession, repo):
        """默认不重复软删已删行（第二次返回 False）"""
        item = (await _make_items(session, 'bob'))[0]
        assert await repo.delete_by_id(session, item.id) is True
        assert await repo.delete_by_id(session, item.id) is False

    async def test_delete_by_id_include_deleted_repeats(self, session: AsyncSession, repo):
        """include_deleted=True 允许对已软删行再次删除"""
        item = (await _make_items(session, 'bob'))[0]
        assert await repo.delete_by_id(session, item.id) is True
        assert await repo.delete_by_id(session, item.id, include_deleted=True) is True

    async def test_delete_where_soft_deletes(self, session: AsyncSession, repo):
        """delete_where 转软删：受影响行默认不可见"""
        items = await _make_items(session, 'a', 'b', 'c')
        deleted = await repo.delete_where(session, name='a')
        assert deleted == 1
        assert await repo.count(session) == 2
        assert await repo.count(session, include_deleted=True) == 3
        # 库中状态由 include_deleted 查询验证（批量 UPDATE 不同步已加载实例）
        fetched = await repo.get(session, items[0].id, include_deleted=True)
        assert fetched is not None and fetched.is_deleted is True

    async def test_hard_delete_by_id(self, session: AsyncSession, repo):
        """hard_delete_by_id 物理删除：include_deleted 也查不到"""
        item = (await _make_items(session, 'bob'))[0]
        assert await repo.hard_delete_by_id(session, item.id) is True
        assert await repo.get(session, item.id, include_deleted=True) is None

    async def test_hard_delete_where(self, session: AsyncSession, repo):
        """hard_delete_where 物理批量删除"""
        await _make_items(session, 'a', 'b', 'c')
        assert await repo.hard_delete_where(session, role='user') == 3
        assert await repo.count(session, include_deleted=True) == 0

    async def test_delete_instance_soft_deletes(self, session: AsyncSession, repo):
        """静态 delete(obj) 对软删模型转软删"""
        item = (await _make_items(session, 'alice'))[0]
        await RepositoryBase.delete(session, item)
        assert item.is_deleted is True
        assert await repo.get(session, item.id) is None
        assert await repo.get(session, item.id, include_deleted=True) is not None

    async def test_soft_delete_uses_deleted_at_timestamp(self, session: AsyncSession, repo):
        """软删写入 deleted_at 时间戳"""
        item = (await _make_items(session, 'ts'))[0]
        await repo.delete_by_id(session, item.id)
        deleted = await repo.get(session, item.id, include_deleted=True)
        assert deleted is not None and deleted.deleted_at is not None


# ── 聚合 ──────────────────────────────────────────────────────────────

class TestRepositoryAggregate:

    async def test_sum(self, session: AsyncSession, repo):
        """sum 求和"""
        await _make_items(session, 'a', 'b', 'c')  # amount: 0, 10, 20
        assert await repo.sum(session, 'amount') == 30

    async def test_avg(self, session: AsyncSession, repo):
        """avg 求平均"""
        await _make_items(session, 'a', 'b', 'c')  # amount: 0, 10, 20
        assert await repo.avg(session, 'amount') == 10

    async def test_min_max(self, session: AsyncSession, repo):
        """min/max 求极值"""
        await _make_items(session, 'a', 'b', 'c')  # amount: 0, 10, 20
        assert await repo.min(session, 'amount') == 0
        assert await repo.max(session, 'amount') == 20

    async def test_aggregate_empty_returns_none(self, session: AsyncSession, repo):
        """空表聚合返回 None"""
        assert await repo.sum(session, 'amount') is None
        assert await repo.avg(session, 'amount') is None

    async def test_aggregate_with_filter(self, session: AsyncSession, repo):
        """聚合支持过滤条件"""
        await _make_items(session, 'a', 'b', 'c')  # amount: 0, 10, 20
        assert await repo.sum(session, 'amount', name='c') == 20

    async def test_aggregate_excludes_soft_deleted(self, session: AsyncSession, repo):
        """聚合默认排除已软删行，include_deleted 放开"""
        items = await _make_items(session, 'a', 'b')  # amount: 0, 10
        await _soft_delete(session, items[1])
        assert await repo.sum(session, 'amount') == 0
        assert await repo.sum(session, 'amount', include_deleted=True) == 10


# ── 批量更新 ──────────────────────────────────────────────────────────

class TestUpdateWhere:

    async def test_update_where_bulk(self, session: AsyncSession, repo):
        """批量更新多行"""
        await _make_items(session, 'a', 'b')
        affected = await repo.update_where(session, {'role': 'admin'})
        assert affected == 2
        assert all(i.role == 'admin' for i in await repo.list(session))

    async def test_update_where_with_filter(self, session: AsyncSession, repo):
        """批量更新带过滤条件"""
        await _make_items(session, 'a', 'b')
        affected = await repo.update_where(session, {'role': 'admin'}, name='a')
        assert affected == 1
        assert await repo.count(session, role='admin') == 1

    async def test_update_where_skips_soft_deleted(self, session: AsyncSession, repo):
        """批量更新默认跳过已软删行，include_deleted 放开"""
        items = await _make_items(session, 'a', 'b')
        await _soft_delete(session, items[0])
        affected = await repo.update_where(session, {'role': 'admin'})
        assert affected == 1
        affected_all = await repo.update_where(
            session, {'role': 'guest'}, include_deleted=True
        )
        assert affected_all == 2

    async def test_update_where_empty_values(self, session: AsyncSession, repo):
        """values 为空返回 0"""
        assert await repo.update_where(session, {}) == 0

    async def test_update_where_invalid_field_raises(self, session: AsyncSession, repo):
        """values 含非法字段抛 AttributeError"""
        await _make_items(session, 'a')
        with pytest.raises(AttributeError, match='no mapped attribute'):
            await repo.update_where(session, {'nonexistent': 1})


# ── 非软删模型回归 ─────────────────────────────────────────────────────

class TestPlainModelRegression:

    async def test_plain_delete_by_id_physical(self, session: AsyncSession, plain_repo):
        """非软删模型 delete_by_id 仍为物理删除"""
        item = PlainItem(name='plain')
        await RepositoryBase.create(session, item)
        assert await plain_repo.delete_by_id(session, item.id) is True
        assert await plain_repo.get(session, item.id) is None

    async def test_plain_delete_where_physical(self, session: AsyncSession, plain_repo):
        """非软删模型 delete_where 仍为物理删除"""
        await RepositoryBase.create_many(
            session, [PlainItem(name='a'), PlainItem(name='b')]
        )
        assert await plain_repo.delete_where(session, name='a') == 1
        assert await plain_repo.count(session) == 1

    async def test_plain_list_not_filtered(self, session: AsyncSession, plain_repo):
        """非软删模型查询无软删过滤（行为不变）"""
        await RepositoryBase.create_many(
            session, [PlainItem(name='a'), PlainItem(name='b')]
        )
        assert len(await plain_repo.list(session)) == 2

    async def test_plain_delete_instance_physical(self, session: AsyncSession, plain_repo):
        """非软删模型静态 delete 仍为物理删除"""
        item = PlainItem(name='plain')
        await RepositoryBase.create(session, item)
        await RepositoryBase.delete(session, item)
        assert await plain_repo.get(session, item.id) is None

    async def test_plain_aggregate(self, session: AsyncSession, plain_repo):
        """非软删模型聚合正常"""
        await RepositoryBase.create_many(
            session,
            [
                PlainItem(name='a'),
                PlainItem(name='b'),
                PlainItem(name='c'),
            ],
        )
        # PlainItem 无 amount 列，用 name 验证 count 类聚合不适用；
        # 这里验证聚合方法在无软删模型上可用（对 id 列 min/max 不受影响）
        assert await plain_repo.max(session, 'id') is not None
