"""
@Author         : hangu
@CreateDate     : 2026/8/31
@Description    : Generic async repository base with create / read / update / delete operations.
"""
from __future__ import annotations

import typing
from collections.abc import Sequence, Mapping
from datetime import datetime, UTC
from functools import lru_cache
from math import ceil
from typing import TypeVar, Generic, cast, Any

from sqlalchemy import (
    func,
    exists,
    select,
    update,
    delete,
    ColumnElement
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from .model_base import ModelBase

ModelT = TypeVar('ModelT', bound=ModelBase)

# paginate 单页数量上限，防止调用方传入超大 size 拖垮数据库
MAX_PAGE_SIZE: int = 1000


class RepositoryBase(Generic[ModelT]):
    """Generic repository for :class:`ModelBase` subclasses.

    Two usage styles are supported:

    **1. Direct instantiation** — pass the model class explicitly::

        user_repo = RepositoryBase(User)

    **2. Subclass** — bind the model via the generic parameter::

        class UserRepo(RepositoryBase[User]):
            ...

        user_repo = UserRepo()

    The session is always passed explicitly, so callers keep full control
    of the transaction boundary — repository methods only *flush*, never *commit*::

        async with factory.transaction() as session:      # auto commit
            await user_repo.create(session, User(name="alice"))

        async with factory.read_session() as session:     # read replica
            users = await user_repo.list(session, is_active=True, limit=10)

    Filters accept both keyword arguments and raw SQLAlchemy expressions::

        await user_repo.list(session, role="admin", expressions=(User.age > 18,))
        await user_repo.list(session, id=["01A", "02B"])   # sequence -> IN
        await user_repo.list(session, name=None)           # None -> IS NULL

    **Soft-delete aware** — when the model mixes in :class:`SoftDeleteMixin`,
    all read methods (``get`` / ``get_unique`` / ``get_first`` / ``list`` /
    ``count`` / ``paginate`` / ``exists``) exclude soft-deleted rows by
    default; pass ``include_deleted=True`` to opt in. Delete methods
    (``delete_by_id`` / ``delete_where`` / ``delete``) turn into a soft
    delete (``is_deleted=True`` + ``deleted_at``) instead of a physical
    DELETE; use ``hard_delete_by_id`` / ``hard_delete_where`` for a real
    removal. Models without ``is_deleted`` behave exactly as before.
    """
    model: type[ModelT]  # The SQLAlchemy model class to operate on.

    def __init__(self, model: type[ModelT] | None = None):
        """Initialize the repository.

        Args:
            model: The SQLAlchemy model class to operate on.
                If *None*, the model is inferred from the generic
                parameter of a subclass (e.g. ``class UserRepo(RepositoryBase[User])``).
        """
        if model is None:
            model = self._resolve_generic_model()

        self.model = model

    @classmethod
    @lru_cache(maxsize=128)
    def _resolve_generic_model(cls: type) -> type[ModelT]:
        """Walk ``__orig_bases__`` to find the concrete model type bound via ``Generic``.

        使用 lru_cache 按子类缓存解析结果，避免每次实例化重复遍历基类

        Returns:
            The resolved model class.

        Raises:
            TypeError: If no model type can be inferred.
        """
        # noinspection PyUnresolvedReferences
        for base in getattr(cls, '__orig_bases__', ()):
            args = typing.get_args(base)
            if args and isinstance(args[0], type) and issubclass(args[0], ModelBase):
                return cast(type[ModelT], args[0])
        raise TypeError(
            f'{cls.__name__} must either pass a model class or '
            f'declare it as a generic parameter (e.g. RepositoryBase[User]).'
        )

    # ── Read ─────────────────────────────────────────────────────────────

    async def get(
            self,
            session: AsyncSession,
            id_: str,
            *,
            include_deleted: bool = False,
    ) -> ModelT | None:
        """Fetch a single row by primary key.

        Checks the session identity map first.

        Args:
            session: The async session to use.
            id_: The primary key value.
            include_deleted: 是否返回已软删除的行（仅软删模型生效，默认 False）

        Returns:
            The model instance, or ``None`` if not found / soft-deleted.
        """
        obj = await session.get(self.model, id_)
        if obj is None:
            return None
        if not include_deleted and getattr(obj, 'is_deleted', False):
            return None
        return obj

    async def get_unique(
            self,
            session: AsyncSession,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> ModelT | None:
        """Fetch exactly zero or one row matching filters.
        If more than one row matches, raises MultipleResultsFound.

        Args:
            session: The async session to use.
            include_deleted: 是否包含已软删除的行（仅软删模型生效，默认 False）
            expressions: Raw SQLAlchemy filter expressions.
            **filters: Equality keyword filters.

        Returns:
            Matching instance if exactly one found, None if no match.

        Raises:
            MultipleResultsFound: More than one row satisfies the filter.
        """
        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )
        stmt = select(self.model).where(*conditions)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_first(
            self,
            session: AsyncSession,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> ModelT | None:
        """Fetch the first row matching the filters.

        Args:
            session: The async session to use.
            include_deleted: 是否包含已软删除的行（仅软删模型生效，默认 False）
            expressions: Raw SQLAlchemy filter expressions.
            **filters: Equality keyword filters.

        Returns:
            The first matching instance, or ``None`` if no row matches.
        """
        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )
        stmt = select(self.model).where(*conditions).limit(1)
        result = await session.execute(stmt)
        return result.scalars().first()

    async def list(
            self,
            session: AsyncSession,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            order_by: Sequence[str | ColumnElement] | None = None,
            offset: int = 0,
            limit: int | None = 100,
            **filters: Any,
    ) -> Sequence[ModelT]:
        """Fetch rows matching the filters with optional ordering / pagination.

        Args:
            session: Async session to run the query on (use a read session).
            include_deleted: 是否包含已软删除的行（仅软删模型生效，默认 False）
            expressions: Raw SQLAlchemy filter expressions.
            order_by: Column expressions or field names; prefix a name with
                ``-`` for descending order (e.g. ``'-created_at'``).
            offset: Number of rows to skip.
            limit: Max rows to return (``None`` = no limit).
            **filters: Equality keyword filters.

        Returns:
            A list of matching model instances.
        """
        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )
        stmt = select(self.model).where(*conditions)

        if order_by:
            stmt = stmt.order_by(*(self._resolve_order(spec) for spec in order_by))

        if offset > 0:
            stmt = stmt.offset(offset)

        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        return result.scalars().all()

    async def count(
            self,
            session: AsyncSession,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int:
        """Count rows matching the filters.

        Args:
            session: The async session to use.
            include_deleted: 是否包含已软删除的行（仅软删模型生效，默认 False）
            expressions: Raw SQLAlchemy filter expressions.
            **filters: Equality keyword filters.

        Returns:
            The number of matching rows.
        """
        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )
        stmt = select(func.count()).select_from(self.model).where(*conditions)
        result = await session.execute(stmt)
        return result.scalar_one()

    async def paginate(
            self,
            session: AsyncSession,
            *,
            page: int = 1,
            size: int = 10,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            order_by: Sequence[str | ColumnElement] | None = None,
            **filters: Any,
    ) -> dict[str, Any]:
        """分页查询，自动执行 count + list 并返回分页结果字典

        内部复用 ``_conditions`` 保证 count 与 list 使用完全相同的过滤条件，
        避免调用方手动写两遍 filter::

            result = await repo.paginate(
                session, page=1, size=10,
                is_active=True, order_by=['-created_at'],
            )
            # result = {'items': [...], 'page': 1, 'size': 10, 'total': 100, 'pages': 10}

            # 可配合 PageData 使用
            from fastapi_augment.schemas import PageData
            page_data = PageData.build(result['items'], page=result['page'],
                                         size=result['size'], total=result['total'])

        Args:
            session: The async session to use (typically a read session).
            page: 当前页码（从 1 开始）
            size: 每页数量
            include_deleted: 是否包含已软删除的行（仅软删模型生效，默认 False）
            expressions: Raw SQLAlchemy filter expressions.
            order_by: Column expressions or field names; prefix ``-`` for descending.
            **filters: Equality keyword filters.

        Returns:
            包含 items / page / size / total / pages 的字典
        """

        page = max(1, page)
        # 上限保护：防止调用方传入超大 size 拖垮数据库
        size = max(1, min(size, MAX_PAGE_SIZE))

        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )

        # count
        count_stmt = select(func.count()).select_from(self.model).where(*conditions)
        total = (await session.execute(count_stmt)).scalar_one()

        # list
        offset = (page - 1) * size
        list_stmt = select(self.model).where(*conditions)

        if order_by:
            list_stmt = list_stmt.order_by(*(self._resolve_order(spec) for spec in order_by))

        list_stmt = list_stmt.offset(offset).limit(size)
        items = (await session.execute(list_stmt)).scalars().all()

        pages = ceil(total / size)
        return {
            'items': items,
            'page': page,
            'size': size,
            'total': total,
            'pages': pages,
        }

    async def exists(
            self,
            session: AsyncSession,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> bool:
        """Check whether at least one row matches the filters.

        Args:
            session: The async session to use.
            include_deleted: 是否包含已软删除的行（仅软删模型生效，默认 False）
            expressions: Raw SQLAlchemy filter expressions.
            **filters: Equality keyword filters.

        Returns:
            ``True`` if at least one matching row exists, ``False`` otherwise.
        """
        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )
        stmt = select(exists().where(*conditions))
        result = await session.execute(stmt)
        return bool(result.scalar())

    # ── Update ───────────────────────────────────────────────────────────

    async def update(self, session: AsyncSession, obj: ModelT, **values: Any) -> ModelT:
        """Update an ORM instance in place.

        Flushes; never commits.

        Args:
            session: The async session to use.
            obj: The model instance to update.
            **values: Field names and their new values.

        Returns:
            The updated model instance.

        Raises:
            AttributeError: If a key does not correspond to a mapped attribute.
        """
        for key in values:
            self._attr(key)

        for key, value in values.items():
            setattr(obj, key, value)

        await session.flush()
        return obj

    async def update_by_id(self, session: AsyncSession, id_: str, **values: Any) -> int:
        """Update a row by primary key with a single UPDATE statement.

        Args:
            session: The async session to use.
            id_: The primary key value.
            **values: Field names and their new values.

        Returns:
            The number of affected rows (0 = not found or nothing to update).
        """
        if not values:
            return 0

        stmt = update(self.model).where(self.model.id == id_).values(**values)
        result = cast(CursorResult[Any], await session.execute(stmt))
        return result.rowcount or 0

    # ── Delete ───────────────────────────────────────────────────────────

    async def delete_by_id(
            self,
            session: AsyncSession,
            id_: str,
            *,
            include_deleted: bool = False,
    ) -> bool:
        """Delete a row by primary key.

        软删模型自动转软删（``is_deleted=True`` + ``deleted_at``），
        非软删模型执行物理删除；需要真正物理删除时用 ``hard_delete_by_id``。

        Args:
            session: The async session to use.
            id_: The primary key value.
            include_deleted: 软删模型上是否允许重复删除已软删行
                （默认 False：已软删行视为不存在，返回 False）

        Returns:
            ``True`` if a row was deleted (or soft-deleted), ``False`` otherwise.
        """
        if self._uses_soft_delete():
            now = datetime.now(UTC)
            stmt = update(self.model).where(self.model.id == id_)
            if not include_deleted:
                stmt = stmt.where(cast(Any, self.model).is_deleted.is_(False))
            stmt = stmt.values(is_deleted=True, deleted_at=now)
            result = cast(CursorResult[Any], await session.execute(stmt))
            # ORM-enabled UPDATE 的 evaluator 同步可能漏掉 deleted_at，
            # 显式同步已加载实例，避免后续读取到 stale 状态
            loaded = await session.get(self.model, id_)
            if loaded is not None:
                loaded = cast(Any, loaded)
                loaded.is_deleted = True
                loaded.deleted_at = now
            return bool(result.rowcount)
        return await self.hard_delete_by_id(session, id_)

    async def hard_delete_by_id(self, session: AsyncSession, id_: str) -> bool:
        """物理删除一行（不经过软删标记，永久删除）.

        Args:
            session: The async session to use.
            id_: The primary key value.

        Returns:
            ``True`` if a row was deleted, ``False`` otherwise.
        """
        stmt = delete(self.model).where(self.model.id == id_)
        result = cast(CursorResult[Any], await session.execute(stmt))
        return bool(result.rowcount)

    async def delete_where(
            self,
            session: AsyncSession,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int:
        """Delete all rows matching the filters.

        软删模型自动转软删（``is_deleted=True`` + ``deleted_at``），
        非软删模型执行物理删除；需要真正物理删除时用 ``hard_delete_where``。

        Args:
            session: The async session to use.
            include_deleted: 软删模型上是否包含已软删的行
                （默认 False：已软删行不参与删除）
            expressions: Raw SQLAlchemy filter expressions.
            **filters: Equality keyword filters.

        Returns:
            The number of deleted (or soft-deleted) rows.
        """
        if self._uses_soft_delete():
            now = datetime.now(UTC)
            conditions = self._apply_soft_delete(
                self._conditions(expressions, filters), include_deleted
            )
            stmt = update(self.model).where(*conditions).values(
                is_deleted=True, deleted_at=now
            )
            result = cast(CursorResult[Any], await session.execute(stmt))
            return result.rowcount or 0
        return await self.hard_delete_where(
            session, expressions=expressions, **filters
        )

    async def hard_delete_where(
            self,
            session: AsyncSession,
            *,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int:
        """物理删除所有匹配行（不经过软删标记，永久删除）.

        Args:
            session: The async session to use.
            expressions: Raw SQLAlchemy filter expressions.
            **filters: Equality keyword filters.

        Returns:
            The number of deleted rows.
        """
        stmt = delete(self.model).where(*self._conditions(expressions, filters))
        result = cast(CursorResult[Any], await session.execute(stmt))
        return result.rowcount or 0

    # ── Soft delete ─────────────────────────────────────────────────────

    def _uses_soft_delete(self) -> bool:
        """模型是否启用软删除（存在 ``is_deleted`` 映射列）

        用于决定查询是否默认过滤已删除行、删除操作是否自动转软删。
        """
        attr = getattr(self.model, 'is_deleted', None)
        return isinstance(attr, InstrumentedAttribute)

    def _soft_delete_condition(self) -> ColumnElement[bool] | None:
        """未删除过滤条件；非软删模型返回 None"""
        if not self._uses_soft_delete():
            return None
        not_deleted = getattr(self.model, 'not_deleted', None)
        if callable(not_deleted):
            return cast(ColumnElement[bool], not_deleted())
        # 兜底：模型只有列没有类方法时按列构造
        return cast(Any, self.model).is_deleted.is_(False)

    def _apply_soft_delete(
            self,
            conditions: Sequence[ColumnElement],
            include_deleted: bool,
    ) -> Sequence[ColumnElement]:
        """软删模型默认追加未删除过滤；``include_deleted=True`` 时原样返回"""
        if include_deleted:
            return list(conditions)
        cond = self._soft_delete_condition()
        if cond is None:
            return list(conditions)
        return [*conditions, cond]

    # ── Aggregate ────────────────────────────────────────────────────────

    async def _aggregate(
            self,
            session: AsyncSession,
            column: str,
            aggregate_func: Any,
            *,
            include_deleted: bool,
            expressions: Sequence[ColumnElement] | None,
            filters: Mapping[str, Any],
    ) -> int | float | None:
        """对指定列执行聚合，自动沿用软删过滤

        Returns:
            聚合结果；无匹配行时返回 None
        """
        col = self._attr(column)
        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )
        stmt = select(aggregate_func(col)).select_from(self.model).where(*conditions)
        result = await session.execute(stmt)
        value = result.scalar_one()
        if value is None:
            return None
        return cast(int | float, value)

    async def sum(
            self,
            session: AsyncSession,
            column: str,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int | float | None:
        """数值列求和（软删模型默认排除已删除行）"""
        return await self._aggregate(
            session, column, func.sum,
            include_deleted=include_deleted, expressions=expressions, filters=filters,
        )

    async def avg(
            self,
            session: AsyncSession,
            column: str,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int | float | None:
        """数值列求平均（软删模型默认排除已删除行）"""
        return await self._aggregate(
            session, column, func.avg,
            include_deleted=include_deleted, expressions=expressions, filters=filters,
        )

    async def min(
            self,
            session: AsyncSession,
            column: str,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int | float | None:
        """数值列最小值（软删模型默认排除已删除行）"""
        return await self._aggregate(
            session, column, func.min,
            include_deleted=include_deleted, expressions=expressions, filters=filters,
        )

    async def max(
            self,
            session: AsyncSession,
            column: str,
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int | float | None:
        """数值列最大值（软删模型默认排除已删除行）"""
        return await self._aggregate(
            session, column, func.max,
            include_deleted=include_deleted, expressions=expressions, filters=filters,
        )

    # ── Bulk update ─────────────────────────────────────────────────────

    async def update_where(
            self,
            session: AsyncSession,
            values: Mapping[str, Any],
            *,
            include_deleted: bool = False,
            expressions: Sequence[ColumnElement] | None = None,
            **filters: Any,
    ) -> int:
        """按条件批量更新多行（单条 UPDATE 语句）

        与 ``delete_where`` 对称；软删模型默认只更新未删除行。

        Args:
            session: The async session to use.
            values: 字段名到新值的映射。
            include_deleted: 软删模型上是否包含已软删的行
                （默认 False：已软删行不参与更新）
            expressions: Raw SQLAlchemy filter expressions.
            **filters: Equality keyword filters.

        Returns:
            受影响的行数（0 = 无匹配或 values 为空）。

        Raises:
            AttributeError: 当 values 中出现不存在的映射字段时。
        """
        if not values:
            return 0
        for key in values:
            self._attr(key)
        conditions = self._apply_soft_delete(
            self._conditions(expressions, filters), include_deleted
        )
        stmt = update(self.model).where(*conditions).values(**values)
        result = cast(CursorResult[Any], await session.execute(stmt))
        return result.rowcount or 0

    # ── Helpers ──────────────────────────────────────────────────────────

    def _attr(self, name: str) -> InstrumentedAttribute[Any]:
        """Resolve a field name to a mapped attribute.

        Args:
            name: The field name to resolve.

        Returns:
            The corresponding :class:`~sqlalchemy.orm.InstrumentedAttribute`.

        Raises:
            AttributeError: If the name does not correspond to a mapped attribute.
        """
        attr = getattr(self.model, name, None)

        if not isinstance(attr, InstrumentedAttribute):
            # 遵循 getattr 语义：缺失字段抛 AttributeError（有意为之，不改 TypeError）
            raise AttributeError(f'{self.model.__name__} has no mapped attribute {name!r}')  # noqa: TRY004

        return attr

    def _conditions(
            self,
            expressions: Sequence[ColumnElement] | None,
            filters: Mapping[str, Any],
    ) -> Sequence[ColumnElement]:
        """Combine raw expressions and keyword filters into WHERE conditions.

        Args:
            expressions: Raw SQLAlchemy filter expressions.
            filters: Equality keyword filters. Sequences (list, set, tuple,
                frozenset) are converted to ``IN`` clauses; ``None`` values
                become ``IS NULL`` checks.

        Returns:
            A list of column expressions suitable for ``.where()``.
        """
        conditions: list[ColumnElement] = list(expressions or [])

        for key, value in filters.items():
            column = self._attr(key)

            if isinstance(value, (list, set, tuple, frozenset)):
                conditions.append(column.in_(value))
            else:
                conditions.append(column == value)

        return conditions

    def _resolve_order(self, spec: str | ColumnElement) -> ColumnElement:
        """Convert an order-by spec into a column expression.

        Args:
            spec: A column expression, or a field name. Prefix with ``-``
                for descending order (e.g. ``'-created_at'``).

        Returns:
            A column expression with the appropriate asc/desc direction.
        """
        if isinstance(spec, str):
            descending = spec.startswith('-')
            column = self._attr(spec.lstrip('+-'))
            return column.desc() if descending else column.asc()

        return spec

    # ── Static Methods ───────────────────────────────────────────────────

    @staticmethod
    async def create(session: AsyncSession, obj: ModelT) -> ModelT:
        """Persist a new object.

        Flushes so PKs / defaults are populated; never commits.

        Args:
            session: The async session to use.
            obj: The model instance to persist.

        Returns:
            The same instance with populated defaults.
        """
        session.add(obj)
        await session.flush()
        return obj

    @staticmethod
    async def create_many(session: AsyncSession, objs: Sequence[ModelT]) -> Sequence[ModelT]:
        """Persist multiple objects in one batch.

        Flushes; never commits.

        Args:
            session: The async session to use.
            objs: The model instances to persist.

        Returns:
            A list of the persisted instances.
        """
        session.add_all(objs)
        await session.flush()
        return objs

    @staticmethod
    async def delete(session: AsyncSession, obj: ModelT) -> None:
        """Delete an ORM instance.

        软删模型自动转软删（``is_deleted=True`` + ``deleted_at``），
        非软删模型执行物理删除。Flushes; never commits.

        Args:
            session: The async session to use.
            obj: The model instance to delete.
        """
        if isinstance(getattr(obj.__class__, 'is_deleted', None), InstrumentedAttribute):
            soft_obj: Any = obj
            soft_obj.is_deleted = True
            soft_obj.deleted_at = datetime.now(UTC)
            await session.flush()
            return
        await session.delete(obj)
        await session.flush()
