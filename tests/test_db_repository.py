"""
db.sqlalchemy.repository_base 模块测试 — RepositoryBase 通用仓储操作

使用 aiosqlite 内存 SQLite 作为测试数据库
"""
import pytest
import pytest_asyncio
from sqlalchemy import String
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

class UserItem(TimestampMixin, SoftDeleteMixin, ModelBase):
    """测试用模型，包含时间戳和软删除"""
    __tablename__ = 'user_items'

    name: Mapped[str] = mapped_column(String(100), comment='名称')
    role: Mapped[str] = mapped_column(String(50), default='user', comment='角色')


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


# ── 子类继承方式仓储 ─────────────────────────────────────────────────

class UserItemRepo(RepositoryBase[UserItem]):
    """通过泛型参数绑定模型的子类仓储"""


@pytest.fixture()
def repo() -> RepositoryBase[UserItem]:
    return RepositoryBase(UserItem)


@pytest.fixture()
def sub_repo() -> UserItemRepo:
    return UserItemRepo()


# ── Create ────────────────────────────────────────────────────────────

class TestRepositoryCreate:

    async def test_create_single(self, session: AsyncSession, repo: RepositoryBase):
        item = UserItem(name='alice', role='admin')
        result = await RepositoryBase.create(session, item)
        assert result.id is not None
        assert len(result.id) == 26  # ULID 长度

    async def test_create_many(self, session: AsyncSession, repo: RepositoryBase):
        items = [
            UserItem(name='bob', role='user'),
            UserItem(name='carol', role='user'),
        ]
        result = await RepositoryBase.create_many(session, items)
        assert len(result) == 2
        assert all(item.id is not None for item in result)


# ── Read ──────────────────────────────────────────────────────────────

class TestRepositoryRead:

    async def test_get_by_id(self, session: AsyncSession, repo: RepositoryBase):
        item = UserItem(name='alice')
        await RepositoryBase.create(session, item)
        fetched = await repo.get(session, item.id)
        assert fetched is not None
        assert fetched.name == 'alice'

    async def test_get_nonexistent_returns_none(self, session: AsyncSession, repo: RepositoryBase):
        result = await repo.get(session, 'nonexistent_id')
        assert result is None

    async def test_get_one_with_filter(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='alice', role='admin'))
        await RepositoryBase.create(session, UserItem(name='bob', role='user'))

        result = await repo.get_first(session, name='bob')
        assert result is not None
        assert result.name == 'bob'

    async def test_get_one_no_match(self, session: AsyncSession, repo: RepositoryBase):
        result = await repo.get_first(session, name='nobody')
        assert result is None

    async def test_get_unique_found(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='alice', role='admin'))
        result = await repo.get_unique(session, name='alice')
        assert result is not None
        assert result.name == 'alice'

    async def test_get_unique_no_match(self, session: AsyncSession, repo: RepositoryBase):
        result = await repo.get_unique(session, name='nobody')
        assert result is None

    async def test_get_unique_multiple_raises(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='alice', role='user'))
        await RepositoryBase.create(session, UserItem(name='alice', role='admin'))
        from sqlalchemy.exc import MultipleResultsFound
        with pytest.raises(MultipleResultsFound):
            await repo.get_unique(session, name='alice')

    async def test_list_all(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='a'))
        await RepositoryBase.create(session, UserItem(name='b'))
        await RepositoryBase.create(session, UserItem(name='c'))

        results = await repo.list(session)
        assert len(results) == 3

    async def test_list_with_filter(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='a', role='admin'))
        await RepositoryBase.create(session, UserItem(name='b', role='user'))
        await RepositoryBase.create(session, UserItem(name='c', role='admin'))

        results = await repo.list(session, role='admin')
        assert len(results) == 2

    async def test_list_with_in_filter(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='a', role='admin'))
        await RepositoryBase.create(session, UserItem(name='b', role='user'))
        await RepositoryBase.create(session, UserItem(name='c', role='guest'))

        results = await repo.list(session, role=['admin', 'guest'])
        assert len(results) == 2

    async def test_list_with_limit(self, session: AsyncSession, repo: RepositoryBase):
        for i in range(5):
            await RepositoryBase.create(session, UserItem(name=f'item_{i}'))

        results = await repo.list(session, limit=3)
        assert len(results) == 3

    async def test_list_with_offset(self, session: AsyncSession, repo: RepositoryBase):
        for i in range(5):
            await RepositoryBase.create(session, UserItem(name=f'item_{i}'))

        results = await repo.list(session, offset=3, limit=None)
        assert len(results) == 2

    async def test_list_with_order_by_asc(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='charlie'))
        await RepositoryBase.create(session, UserItem(name='alice'))
        await RepositoryBase.create(session, UserItem(name='bob'))

        results = await repo.list(session, order_by=['name'], limit=None)
        names = [r.name for r in results]
        assert names == ['alice', 'bob', 'charlie']

    async def test_list_with_order_by_desc(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='alice'))
        await RepositoryBase.create(session, UserItem(name='charlie'))
        await RepositoryBase.create(session, UserItem(name='bob'))

        results = await repo.list(session, order_by=['-name'], limit=None)
        names = [r.name for r in results]
        assert names == ['charlie', 'bob', 'alice']


# ── Count / Exists ────────────────────────────────────────────────────

class TestRepositoryCountExists:

    async def test_count_all(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='a'))
        await RepositoryBase.create(session, UserItem(name='b'))
        assert await repo.count(session) == 2

    async def test_count_with_filter(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='a', role='admin'))
        await RepositoryBase.create(session, UserItem(name='b', role='user'))
        assert await repo.count(session, role='admin') == 1

    async def test_exists_true(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='alice'))
        assert await repo.exists(session, name='alice') is True

    async def test_exists_false(self, session: AsyncSession, repo: RepositoryBase):
        assert await repo.exists(session, name='nobody') is False


# ── Update ────────────────────────────────────────────────────────────

class TestRepositoryUpdate:

    async def test_update_instance(self, session: AsyncSession, repo: RepositoryBase):
        item = UserItem(name='alice', role='user')
        await RepositoryBase.create(session, item)
        updated = await repo.update(session, item, name='alice_updated')
        assert updated.name == 'alice_updated'

    async def test_update_by_id(self, session: AsyncSession, repo: RepositoryBase):
        item = UserItem(name='bob')
        await RepositoryBase.create(session, item)
        affected = await repo.update_by_id(session, item.id, name='bob_updated')
        assert affected == 1

        fetched = await repo.get(session, item.id)
        assert fetched.name == 'bob_updated'

    async def test_update_by_id_not_found(self, session: AsyncSession, repo: RepositoryBase):
        affected = await repo.update_by_id(session, 'nonexistent', name='x')
        assert affected == 0

    async def test_update_by_id_empty_values(self, session: AsyncSession, repo: RepositoryBase):
        affected = await repo.update_by_id(session, 'some_id')
        assert affected == 0

    async def test_update_invalid_field_raises(self, session: AsyncSession, repo: RepositoryBase):
        item = UserItem(name='alice')
        await RepositoryBase.create(session, item)
        with pytest.raises(AttributeError, match='no mapped attribute'):
            await repo.update(session, item, nonexistent_field='value')


# ── Delete ────────────────────────────────────────────────────────────

class TestRepositoryDelete:

    async def test_delete_instance(self, session: AsyncSession, repo: RepositoryBase):
        item = UserItem(name='alice')
        await RepositoryBase.create(session, item)
        await RepositoryBase.delete(session, item)
        assert await repo.get(session, item.id) is None

    async def test_delete_by_id(self, session: AsyncSession, repo: RepositoryBase):
        item = UserItem(name='bob')
        await RepositoryBase.create(session, item)
        result = await repo.delete_by_id(session, item.id)
        assert result is True
        assert await repo.get(session, item.id) is None

    async def test_delete_by_id_not_found(self, session: AsyncSession, repo: RepositoryBase):
        result = await repo.delete_by_id(session, 'nonexistent')
        assert result is False

    async def test_delete_where(self, session: AsyncSession, repo: RepositoryBase):
        await RepositoryBase.create(session, UserItem(name='a', role='temp'))
        await RepositoryBase.create(session, UserItem(name='b', role='temp'))
        await RepositoryBase.create(session, UserItem(name='c', role='keep'))

        deleted = await repo.delete_where(session, role='temp')
        assert deleted == 2
        assert await repo.count(session) == 1


# ── 辅助方法 ─────────────────────────────────────────────────────────

class TestRepositoryHelpers:

    def test_attr_valid(self, repo: RepositoryBase):
        attr = repo._attr('name')
        assert attr is not None

    def test_attr_invalid_raises(self, repo: RepositoryBase):
        with pytest.raises(AttributeError, match='no mapped attribute'):
            repo._attr('nonexistent')

    def test_conditions_with_expressions(self, session: AsyncSession, repo: RepositoryBase):
        """raw expressions 被正确合并"""
        conditions = repo._conditions(
            expressions=(UserItem.name == 'test',),
            filters={'role': 'admin'},
        )
        assert len(conditions) == 2

    def test_conditions_none_value_becomes_is_null(self, repo: RepositoryBase):
        """None 值过滤条件"""
        conditions = repo._conditions(None, {'name': None})
        assert len(conditions) == 1

    def test_resolve_order_string_asc(self, repo: RepositoryBase):
        result = repo._resolve_order('name')
        assert result is not None

    def test_resolve_order_string_desc(self, repo: RepositoryBase):
        result = repo._resolve_order('-name')
        assert result is not None

    def test_resolve_order_with_plus_prefix(self, repo: RepositoryBase):
        result = repo._resolve_order('+name')
        assert result is not None

    def test_resolve_order_column_expression(self, repo: RepositoryBase):
        col_expr = UserItem.name.asc()
        result = repo._resolve_order(col_expr)
        assert result is col_expr


# ── 子类继承方式 ─────────────────────────────────────────────────────

class TestRepositorySubclass:
    """测试通过子类继承 + 泛型参数绑定模型的方式"""

    def test_subclass_resolves_model(self, sub_repo: UserItemRepo):
        """子类仓储正确解析泛型参数为 model 类"""
        assert sub_repo.model is UserItem

    def test_subclass_override_model(self):
        """子类实例化时仍可显式传入 model 覆盖"""
        repo = UserItemRepo(UserItem)
        assert repo.model is UserItem

    async def test_subclass_get(self, session: AsyncSession, sub_repo: UserItemRepo):
        """子类仓储的 CRUD 操作正常工作"""
        item = UserItem(name='sub_test')
        await RepositoryBase.create(session, item)
        fetched = await sub_repo.get(session, item.id)
        assert fetched is not None
        assert fetched.name == 'sub_test'

    async def test_subclass_list(self, session: AsyncSession, sub_repo: UserItemRepo):
        """子类仓储的 list 操作正常"""
        await RepositoryBase.create(session, UserItem(name='a', role='admin'))
        await RepositoryBase.create(session, UserItem(name='b', role='user'))
        results = await sub_repo.list(session, role='admin')
        assert len(results) == 1
        assert results[0].name == 'a'

    async def test_subclass_count(self, session: AsyncSession, sub_repo: UserItemRepo):
        """子类仓储的 count 操作正常"""
        await RepositoryBase.create(session, UserItem(name='x'))
        await RepositoryBase.create(session, UserItem(name='y'))
        assert await sub_repo.count(session) == 2

    async def test_subclass_paginate(self, session: AsyncSession, sub_repo: UserItemRepo):
        """子类仓储的 paginate 操作正常"""
        for i in range(5):
            await RepositoryBase.create(session, UserItem(name=f'sub_{i}', role='user'))
        result = await sub_repo.paginate(session, page=1, size=3)
        assert result['total'] == 5
        assert len(result['items']) == 3

    def test_no_model_raises_type_error(self):
        """既无泛型参数又无显式 model 时抛出 TypeError"""
        class BadRepo(RepositoryBase):  # type: ignore[type-arg]
            pass

        with pytest.raises(TypeError, match='must either pass a model class'):
            BadRepo()


# ── Paginate ──────────────────────────────────────────────────────────

class TestRepositoryPaginate:

    async def test_paginate_returns_dict(self, session: AsyncSession, repo: RepositoryBase):
        """paginate 返回正确的分页字典结构"""
        for i in range(5):
            await RepositoryBase.create(session, UserItem(name=f'user_{i}', role='user'))

        result = await repo.paginate(session, page=1, size=3)

        assert result['page'] == 1
        assert result['size'] == 3
        assert result['total'] == 5
        assert result['pages'] == 2
        assert len(result['items']) == 3

    async def test_paginate_second_page(self, session: AsyncSession, repo: RepositoryBase):
        """paginate 第二页数据正确"""
        for i in range(5):
            await RepositoryBase.create(session, UserItem(name=f'user_{i}', role='user'))

        result = await repo.paginate(session, page=2, size=3)

        assert result['page'] == 2
        assert result['total'] == 5
        assert result['pages'] == 2
        assert len(result['items']) == 2

    async def test_paginate_with_filters(self, session: AsyncSession, repo: RepositoryBase):
        """paginate 过滤条件同时作用于 count 和 list"""
        await RepositoryBase.create(session, UserItem(name='admin', role='admin'))
        await RepositoryBase.create(session, UserItem(name='user1', role='user'))
        await RepositoryBase.create(session, UserItem(name='user2', role='user'))

        result = await repo.paginate(session, page=1, size=10, role='admin')

        assert result['total'] == 1
        assert len(result['items']) == 1
        assert result['items'][0].name == 'admin'

    async def test_paginate_empty(self, session: AsyncSession, repo: RepositoryBase):
        """无数据时返回空列表、total=0"""
        result = await repo.paginate(session, page=1, size=10)

        assert result['total'] == 0
        assert result['pages'] == 0
        assert len(result['items']) == 0

    async def test_paginate_with_order(self, session: AsyncSession, repo: RepositoryBase):
        """paginate 支持排序"""
        await RepositoryBase.create(session, UserItem(name='charlie', role='user'))
        await RepositoryBase.create(session, UserItem(name='alice', role='user'))
        await RepositoryBase.create(session, UserItem(name='bob', role='user'))

        result = await repo.paginate(session, page=1, size=10, order_by=['name'])

        names = [item.name for item in result['items']]
        assert names == ['alice', 'bob', 'charlie']

    async def test_paginate_size_capped(self, session: AsyncSession, repo: RepositoryBase):
        """paginate 的 size 超上限时被截断为 MAX_PAGE_SIZE"""
        from fastapi_augment.db.sqlalchemy.repository_base import MAX_PAGE_SIZE

        for i in range(5):
            await RepositoryBase.create(session, UserItem(name=f'user_{i}', role='user'))

        result = await repo.paginate(session, page=1, size=MAX_PAGE_SIZE * 10)
        assert result['size'] == MAX_PAGE_SIZE
        assert len(result['items']) == 5
