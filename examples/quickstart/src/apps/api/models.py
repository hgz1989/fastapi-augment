"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 示例业务模型——展示 TimestampMixin + SoftDeleteMixin 组合
"""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_augment.db.sqlalchemy import ModelBase
from fastapi_augment.db.sqlalchemy.mixins import SoftDeleteMixin, TimestampMixin


class Item(TimestampMixin, SoftDeleteMixin, ModelBase):
    """商品模型（软删除示例）

    混入 SoftDeleteMixin 后，RepositoryBase 自动感知：
    查询默认过滤已删除行、删除操作自动转软删。
    """
    __tablename__ = 'items'

    name: Mapped[str] = mapped_column(String(100), comment='名称')
    price: Mapped[int] = mapped_column(Integer, default=0, comment='价格（分）')
