"""
@Author         : hangu
@CreateDate     : 2026/9/1
@Description    : 分页响应模型 PageData，对外输出，继承APISchemaBase
"""
from __future__ import annotations

from collections.abc import Sequence
from math import ceil
from typing import Generic

from pydantic import Field

from .base import SchemaBase
from .types import T


class PageData(SchemaBase, Generic[T]):
    """通用分页返回体"""
    items: Sequence[T] = Field(default_factory=list, description='当前页数据列表')
    page: int = Field(default=1, description='当前页码')
    size: int = Field(default=10, description='每页数量')
    pages: int = Field(default=0, description='总页数')
    total: int = Field(default=0, description='总记录数')

    @classmethod
    def build(
            cls,
            items: list[T] | Sequence[T],
            *,
            page: int,
            size: int,
            total: int
    ) -> PageData[T]:
        """构建分页对象，自动计算总页数

        Args:
            items: 当前页数据列表
            page: 当前页码
            size: 每页数量
            total: 总记录数

        Returns:
            分页对象
        """
        pages = ceil(total / size) if size > 0 else 0
        return cls(items=items, page=page, size=size, pages=pages, total=total)
