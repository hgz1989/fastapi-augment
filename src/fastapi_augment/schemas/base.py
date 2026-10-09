"""
@Author         : hangu
@CreateDate     : 2026/9/1
@Description    : Schema全局基类
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class SchemaBase(BaseModel):
    """
    API对外输出基类：仅用于接口返回JSON，**不做ORM读取**
    关闭 from_attributes，避免误用；保留驼峰、时间序列化
    """
    model_config = ConfigDict(
        populate_by_name=True,
        extra='ignore',
        alias_generator=to_camel
    )


class ORMSchemaBase(SchemaBase):
    """全局所有Pydantic Schema基类
    统一配置、统一行为
    """
    # Pydantic 会自动继承父类 model_config（populate_by_name/extra/alias_generator），
    # 无需 **SchemaBase.model_config 重复展开（Pyright 会报参数重复赋值）；
    # 这里只需补充 from_attributes 与 arbitrary_types_allowed
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )
