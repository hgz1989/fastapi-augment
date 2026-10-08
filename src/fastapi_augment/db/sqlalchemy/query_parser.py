"""
@Author         : hangu
@CreateDate     : 2026/9/10
@Description    : 通用查询参数解析器

将 REST 风格的 query string 转为 SQLAlchemy ColumnElement 条件表达式
分隔符采用 Kubernetes field-selector 风格，避免值中出现 ``:`` 导致歧义

支持的 where 表达式语法（FIQL 风格，; 优先级高于 ,）::

    where = and_group ("," and_group)*        , 表示 OR
    and_group = unit (";" unit)*              ; 表示 AND
    unit  = "(" where ")" | condition         括号分组
    condition = field OP value

支持的操作符::

    field==value        等于
    field!=value        不等（NOT）
    field~=value        模糊包含（ILIKE %value%）
    field>value         大于
    field>=value        大于等于
    field<value         小于
    field<=value        小于等于
    field~start~end     区间（between）

示例::

    where=nickname~=张;status!=0                        昵称含张 且 状态非禁用
    where=(nickname~=张,username~=王);gender~0~2         括号内 OR，与区间 AND
    where=created_at>=2026-01-01;(phone==138,phone==139)

其余参数::

    q       = admin                            关键字搜索（多字段 OR）
    q_field = username,email,nickname          关键字搜索字段
    sort    = -created_at,nickname             排序（- 前缀表示降序）

值中包含 ``:`` ``=`` 等字符时不受影响，因为分隔符只在第一个匹配处切分
所有解析函数均校验字段必须是模型的映射列，防止注入与属性访问越权；
各解析函数还支持可选 ``fields`` 白名单参数，由调用方进一步收窄可用字段
"""
from collections.abc import Collection, Sequence
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import (
    ColumnElement,
    and_,
    or_,
    desc,
    asc
)
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import (
    UnaryExpression
)

from fastapi_augment.common import BadRequestError
from fastapi_augment.db.sqlalchemy import (
    ModelBase
)


def _escape_like(value: str) -> str:
    """转义 ILIKE 通配符，防止用户输入 % 或 _ 导致意外匹配

    Args:
        value: 原始字符串

    Returns:
        转义后的字符串，% → \\%，_ → \\_
    """
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


@lru_cache(maxsize=256)
def _get_column(model: type[ModelBase], field: str) -> Any:
    """获取模型上指定字段的列对象（lru_cache 缓存，避免重复 getattr）

    仅接受真正的映射列（InstrumentedAttribute）；类方法 / 普通类属性
    （如 ``not_deleted``、``__tablename__``）一律拒绝，否则后续访问
    ``column.type`` 会抛 AttributeError 变成 500 而非 400。

    Args:
        model: SQLAlchemy 模型类
        field: 字段名

    Returns:
        对应的 InstrumentedAttribute 列对象

    Raises:
        BadRequestError: 字段名不存在于模型上或不是映射列
    """
    column = getattr(model, field, None)
    if not isinstance(column, InstrumentedAttribute):
        raise BadRequestError(detail=f'不支持的查询字段: {field}')
    return column


def _convert_value(python_type: type, value: str) -> Any:
    """根据列的 Python 类型将字符串值转换为对应类型

    转换失败立即抛 BadRequestError（400），而不是静默返回原始字符串——
    静默回退会把错误延迟到数据库执行时才暴露成 500。

    Args:
        python_type: 列的 Python 类型
        value: 原始字符串值

    Returns:
        转换后的值（int / bool / datetime / str）

    Raises:
        BadRequestError: 值无法转换为目标类型
    """
    try:
        if python_type is bool:
            result: Any = value.lower() in ('true', '1', 'yes')
        elif python_type is datetime:
            result = datetime.fromisoformat(value)
        else:
            result = python_type(value)
    except (ValueError, TypeError) as e:
        # 经 Any 中转：PyCharm 对静态类型 type 的值做 str/repr 转换会报弱警告，Any 可阻断该推断
        raw: Any = python_type
        type_name = getattr(raw, '__name__', repr(raw))
        raise BadRequestError(
            detail=f'值 {value!r} 无法转换为 {type_name} 类型'
        ) from e
    return result


def parse_lookup(
        raw: str,
        model: type[ModelBase],
        fields: Collection[str],
) -> ColumnElement:
    """解析 lookup 端点的精确匹配条件，支持单个或多个AND等值条件，单元使用 ; 分隔

    Args:
        raw: 原始 filter 字符串，格式 ``key==value``，多条件用 ; 分隔，全部为AND关系
        model: SQLAlchemy 模型类
        fields: 允许精确匹配的字段白名单（业务唯一字段由调用方定义）

    Returns:
        精确匹配的等值条件表达式

    Raises:
        BadRequestError: 格式错误或字段不在白名单
    """
    units = raw.split(';')
    conds: list[ColumnElement] = []
    seen_fields: set[str] = set()

    for unit in units:
        unit = unit.strip()
        if not unit:
            continue

        if '==' not in unit:
            raise BadRequestError(detail='filter 单元格式错误，应为 key==value')

        field, _, value = unit.partition('==')
        field = field.strip()
        value = value.strip()

        # 【优化1】禁止同一个字段重复传入
        if field in seen_fields:
            raise BadRequestError(detail=f'lookup 不可重复指定字段: {field}')
        seen_fields.add(field)

        if field not in fields:
            raise BadRequestError(
                detail=f'lookup 仅支持字段: {", ".join(sorted(fields))}'
            )

        if not value:
            raise BadRequestError(detail=f'filter 字段 {field} 的 value 不能为空')

        column = _get_column(model, field)
        conds.append(column == _convert_value(column.type.python_type, value))

    if not conds:
        raise BadRequestError(detail='filter 至少需要一个有效查询条件')

    if len(conds) == 1:
        return conds[0]
    return and_(*conds)


# 括号最大嵌套深度，防止病态输入触发 RecursionError 变成 500
_MAX_PAREN_DEPTH = 32


class _WhereParser:
    """where 表达式递归下降解析器

    语法（; 优先级高于 ,）::

        expr  := and_group ("," and_group)*        , 表示 OR
        and_group := unit (";" unit)*              ; 表示 AND
        unit  := "(" expr ")" | condition
        condition := field OP value

    Attributes:
        _src: 原始表达式字符串
        _pos: 当前解析位置
        _model: SQLAlchemy 模型类
        _fields: 调用方指定的字段白名单；None 表示允许模型全部映射列
        _depth: 当前括号嵌套深度
    """

    # 多字符操作符优先匹配，避免 >= 被 > 截断
    _OPERATORS = ('>=', '<=', '==', '!=', '~=', '>', '<', '~')

    def __init__(
            self,
            source: str,
            model: type[ModelBase],
            fields: Collection[str] | None = None,
    ):
        self._src = source
        self._pos = 0
        self._model = model
        self._fields = frozenset(fields) if fields is not None else None
        self._depth = 0

    def parse(self) -> ColumnElement:
        """解析完整表达式

        Returns:
            组合后的条件表达式

        Raises:
            BadRequestError: 表达式语法错误
        """
        expr = self._parse_or()
        self._skip_ws()
        if self._pos < len(self._src):
            raise BadRequestError(detail=f'where 表达式位置 {self._pos} 存在多余字符')
        return expr

    def _parse_or(self) -> ColumnElement:
        """解析 OR 层（优先级最低）"""
        items = [self._parse_and()]
        while self._match(','):
            items.append(self._parse_and())
        return items[0] if len(items) == 1 else or_(*items)

    def _parse_and(self) -> ColumnElement:
        """解析 AND 层（优先级高于 OR）"""
        items = [self._parse_unit()]
        while self._match(';'):
            items.append(self._parse_unit())
        return items[0] if len(items) == 1 else and_(*items)

    def _parse_unit(self) -> ColumnElement:
        """解析单元：括号分组或单个条件"""
        self._skip_ws()
        if self._peek() == '(':
            if self._depth >= _MAX_PAREN_DEPTH:
                raise BadRequestError(
                    detail=f'where 表达式括号嵌套超过 {_MAX_PAREN_DEPTH} 层'
                )
            self._depth += 1
            self._pos += 1
            expr = self._parse_or()
            if self._peek() != ')':
                raise BadRequestError(detail='where 表达式缺少右括号 )')
            self._pos += 1
            self._depth -= 1
            return expr
        return self._parse_condition()

    def _parse_condition(self) -> ColumnElement:
        """解析单个比较条件: field OP value

        Raises:
            BadRequestError: 缺少字段名 / 操作符 / 值
        """
        # 读取字段名（字母数字下划线）
        start = self._pos
        while self._pos < len(self._src) and (
                self._src[self._pos].isalnum() or self._src[self._pos] == '_'):
            self._pos += 1
        field = self._src[start:self._pos]
        if not field:
            raise BadRequestError(detail=f'where 表达式位置 {self._pos} 缺少字段名')

        if self._fields is not None and field not in self._fields:
            raise BadRequestError(
                detail=f'where 仅支持字段: {", ".join(sorted(self._fields))}'
            )

        # 匹配操作符
        self._skip_ws()
        for op in self._OPERATORS:
            if self._src.startswith(op, self._pos):
                self._pos += len(op)
                break
        else:
            raise BadRequestError(
                detail=f'where 表达式位置 {self._pos} 缺少操作符（== != ~= > >= < <= ~）'
            )

        # 读取值直到逻辑分隔符 / 右括号 / 结尾
        self._skip_ws()
        value_start = self._pos
        while self._pos < len(self._src) and self._src[self._pos] not in ',;)':
            self._pos += 1
        raw_value = self._src[value_start:self._pos].strip()
        if not raw_value:
            raise BadRequestError(detail=f'{field} 的 value 不能为空')

        column = _get_column(self._model, field)
        return self._build_condition(column, op, raw_value)

    @staticmethod
    def _build_condition(column: Any, op: str, raw_value: str) -> ColumnElement:
        """根据操作符构建 SQLAlchemy 条件

        Args:
            column: 模型列对象
            op: 操作符
            raw_value: 原始值字符串

        Returns:
            对应的条件表达式

        Raises:
            BadRequestError: between 格式错误或值类型转换失败
        """
        if op == '==':
            return column == _convert_value(column.type.python_type, raw_value)
        if op == '!=':
            return column != _convert_value(column.type.python_type, raw_value)
        if op == '~=':
            return column.ilike(f'%{_escape_like(raw_value)}%')
        if op == '>':
            return column > _convert_value(column.type.python_type, raw_value)
        if op == '>=':
            return column >= _convert_value(column.type.python_type, raw_value)
        if op == '<':
            return column < _convert_value(column.type.python_type, raw_value)
        if op == '<=':
            return column <= _convert_value(column.type.python_type, raw_value)

        # between: value 应为 start~end
        parts = raw_value.split('~')
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise BadRequestError(detail=f'between 格式错误，应为 field~start~end: {raw_value}')
        return column.between(
            _convert_value(column.type.python_type, parts[0].strip()),
            _convert_value(column.type.python_type, parts[1].strip()),
        )

    def _match(self, ch: str) -> bool:
        """跳过空白后匹配指定字符，匹配成功则消费它"""
        self._skip_ws()
        if self._peek() == ch:
            self._pos += 1
            return True
        return False

    def _peek(self) -> str:
        """查看当前字符不消费，越界返回空串"""
        return self._src[self._pos] if self._pos < len(self._src) else ''

    def _skip_ws(self) -> None:
        """跳过空白字符"""
        while self._pos < len(self._src) and self._src[self._pos].isspace():
            self._pos += 1


def parse_where(
        where: str,
        model: type[ModelBase],
        *,
        fields: Collection[str] | None = None,
) -> ColumnElement:
    """解析 where 组合条件表达式（支持与或非 + 括号分组）

    Args:
        where: 原始 where 表达式字符串
        model: SQLAlchemy 模型类
        fields: 允许查询的字段白名单；None 表示允许模型全部映射列

    Returns:
        组合后的条件表达式

    Raises:
        BadRequestError: 表达式语法错误或字段不在白名单
    """
    return _WhereParser(where, model, fields).parse()


def parse_keyword(
        q: str,
        q_field: str,
        model: type[ModelBase],
        *,
        fields: Collection[str] | None = None,
) -> ColumnElement | None:
    """解析关键字搜索条件（多字段 OR）

    Args:
        q: 关键字
        q_field: 搜索字段列表，逗号分隔
        model: SQLAlchemy 模型类
        fields: 允许搜索的字段白名单；None 表示允许模型全部映射列

    Returns:
        多字段 OR 的 ILIKE 条件表达式，无有效字段时返回 None

    Raises:
        BadRequestError: 字段名不存在或不在白名单
    """
    allowed = frozenset(fields) if fields is not None else None
    conditions = []
    for field in q_field.split(','):
        field = field.strip()
        if not field:
            continue
        if allowed is not None and field not in allowed:
            raise BadRequestError(
                detail=f'关键字搜索仅支持字段: {", ".join(sorted(allowed))}'
            )
        column = _get_column(model, field)
        conditions.append(column.ilike(f'%{_escape_like(q)}%'))

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return or_(*conditions)


def parse_sort(
        raw: str,
        model: type[ModelBase],
        *,
        fields: Collection[str] | None = None,
) -> list[UnaryExpression]:
    """解析排序字段

    Args:
        raw: 原始 sort 字符串，``field`` 升序，``-field`` 降序
        model: SQLAlchemy 模型类
        fields: 允许排序的字段白名单；None 表示允许模型全部映射列

    Returns:
        排序表达式列表

    Raises:
        BadRequestError: 字段名不存在或不在白名单
    """
    allowed = frozenset(fields) if fields is not None else None
    result = []
    for field in raw.split(','):
        field = field.strip()
        if not field:
            continue
        name = field[1:] if field.startswith('-') else field
        if allowed is not None and name not in allowed:
            raise BadRequestError(
                detail=f'sort 仅支持字段: {", ".join(sorted(allowed))}'
            )
        column = _get_column(model, name)
        result.append(desc(column) if field.startswith('-') else asc(column))
    return result


def build_query_expressions(
        model: type[ModelBase],
        *,
        where: str | None = None,
        q: str | None = None,
        q_field: str | None = None,
        sort: str | None = None,
        fields: Collection[str] | None = None,
) -> tuple[Sequence[ColumnElement], Sequence[UnaryExpression]]:
    """汇总所有列表查询条件

    组合逻辑: where 表达式 AND keyword 条件

    Args:
        model: SQLAlchemy 模型类
        where: 组合条件表达式（支持 ; 与 , 或 != 非 () 分组）
        q: 关键字
        q_field: 关键字搜索字段列表
        sort: 排序原始字符串
        fields: 允许查询 / 排序的字段白名单；None 表示允许模型全部映射列

    Returns:
        (expressions, order_by) 元组，分别传给 paginate

    Raises:
        BadRequestError: 任一解析过程失败
    """
    expressions: list[ColumnElement] = []

    # where 组合条件
    if where:
        expressions.append(parse_where(where, model, fields=fields))

    # 关键字（多字段 OR）
    if q and q_field:
        keyword_condition = parse_keyword(q, q_field, model, fields=fields)
        if keyword_condition is not None:
            expressions.append(keyword_condition)

    # 排序
    order_by = parse_sort(sort, model, fields=fields) if sort else []

    return expressions, order_by
