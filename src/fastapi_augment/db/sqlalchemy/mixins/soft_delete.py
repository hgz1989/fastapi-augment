"""
@Author         : hangu
@CreateDate     : 2026/9/1
@Description    : 软删除混入类，提供 is_deleted / deleted_at 通用列
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ColumnExpressionArgument,
    String
)
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """软删除混入类

    为模型添加 is_deleted / deleted_at 两列，配合 RepositoryBase 使用::

        # 标记删除（service 层负责）
        await repo.update_by_id(
            session, uid,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc),
        )

        # 只查询未删除数据
        await repo.list(session, expressions=(User.not_deleted(),))

    注意：软删除只是应用层约定，数据库的唯一约束、外键等
    不会感知软删状态（软删行仍占用唯一键），需在业务层处理
    """

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        comment='是否已删除',
        sort_order=920
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        comment='删除时间',
        sort_order=921
    )

    @classmethod
    def not_deleted(cls) -> ColumnExpressionArgument[bool]:
        """未删除的过滤条件"""
        return cls.is_deleted.is_(False)

    @classmethod
    def only_deleted(cls) -> ColumnExpressionArgument[bool]:
        """已删除的过滤条件"""
        return cls.is_deleted.is_(True)


class SoftDeleteAuditMixin(SoftDeleteMixin):
    """带操作人审计的软删除扩展 Mixin

    在基础软删之上增加 deleted_by，记录是谁执行软删除
    需要审计删除人的模型再继承本类，不要全局滥用

    使用示例::
        await repo.update_by_id(
            session,
            uid,
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc),
            deleted_by=operator_user_id,
        )
    """

    # 根据你的主键类型调整：ULID / str / int，这里示例用 str，可改成 ULID
    deleted_by: Mapped[str | None] = mapped_column(
        String(26),
        default=None,
        comment='执行软删除操作人ID',
        sort_order=922
    )
