"""
@Author         : hangu
@CreateDate     : 2026/9/1
@Description    : 请求参数定义
"""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import SchemaBase


class PageParams(SchemaBase):
    """通用分页请求参数"""
    page: int = Field(default=1, description='当前页码', ge=1)
    size: int = Field(default=100, description='每页数量', ge=1, le=1000)


class TimeRangeParams(SchemaBase):
    """通用时间范围查询参数"""
    start_time: datetime | None = Field(default=None, description='开始时间')
    end_time: datetime | None = Field(default=None, description='结束时间')


class KeywordParams(SchemaBase):
    """通用关键字搜索参数"""
    keyword: str | None = Field(default=None, description='搜索关键字', max_length=100)
