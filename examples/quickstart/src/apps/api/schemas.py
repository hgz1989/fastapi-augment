"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 示例 DTO——SchemaBase（请求）/ ORMSchemaBase（响应），统一驼峰输出
"""
from datetime import datetime

from fastapi_augment.schemas import ORMSchemaBase, SchemaBase
from pydantic import Field


class ItemCreate(SchemaBase):
    """创建 / 更新商品请求"""
    name: str = Field(..., description='名称', examples=['示例商品'])
    price: int = Field(0, description='价格（分）', examples=[9900])


class ItemOut(ORMSchemaBase):
    """商品响应（驼峰输出：isDeleted / createdAt）"""
    id: str = Field(..., description='ULID 主键')
    name: str = Field(..., description='名称')
    price: int = Field(..., description='价格（分）')
    is_deleted: bool = Field(default=False, description='是否已软删')
    created_at: datetime | None = Field(default=None, description='创建时间')
