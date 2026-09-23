"""
@Author         : hangu
@CreateDate     : 2026/9/1
@Description    : 泛型类型变量定义
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import TypeVar, Any, Annotated

from pydantic import GetJsonSchemaHandler
from pydantic_core import CoreSchema, core_schema

T = TypeVar('T')
E = TypeVar('E')  # 扩展结构体
BEIJING_TZ = timezone(timedelta(hours=8))


def serialize_beijing_dt(dt: datetime) -> str:
    """
    输入：数据库读出的UTC带时区datetime
    输出：北京时间字符串 yyyy-MM-dd HH:mm:ss.fff
    """
    bj_dt = dt.astimezone(BEIJING_TZ)
    return bj_dt.isoformat(sep=' ', timespec='milliseconds')


class _BeijingDatetimePydantic:
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: GetJsonSchemaHandler) -> CoreSchema:
        return core_schema.datetime_schema(
            serialization=core_schema.plain_serializer_function_ser_schema(serialize_beijing_dt)
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema, handler: GetJsonSchemaHandler) -> dict[str, Any]:
        json_schema = handler(_core_schema)
        json_schema.update(
            type='string',
            description='数据库存储UTC时间；接口返回北京时间(UTC+8)，格式 yyyy-MM-dd HH:mm:ss.fff',
            example='2026-11-12 12:33:22.999'
        )
        return json_schema


BeijingDatetime = Annotated[datetime, _BeijingDatetimePydantic]
