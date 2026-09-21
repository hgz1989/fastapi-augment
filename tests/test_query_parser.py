"""
db.sqlalchemy.query_parser 模块测试
"""
from datetime import datetime

import pytest
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime
)
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_augment.common.exceptions import (
    BadRequestError
)
from fastapi_augment.db.sqlalchemy.model_base import (
    ModelBase
)
from fastapi_augment.db.sqlalchemy.query_parser import (
    _escape_like,
    _get_column,
    _convert_value,
    parse_lookup,
    parse_where,
    parse_keyword,
    parse_sort,
    build_query_expressions
)


class SampleModel(ModelBase):
    __tablename__ = 'qp_samples'
    name: Mapped[str] = mapped_column(String(100), comment='名称')
    age: Mapped[int] = mapped_column(Integer, default=0, comment='年龄')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment='是否激活')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment='创建时间')


class TestEscapeLike:
    def test_plain(self):
        assert _escape_like('hello') == 'hello'

    def test_percent(self):
        assert _escape_like('100%') == '100\\%'

    def test_underscore(self):
        assert _escape_like('a_b') == 'a\\_b'

    def test_backslash(self):
        assert _escape_like('a\\b') == 'a\\\\b'

    def test_mixed(self):
        assert _escape_like('a%b_c\\d') == 'a\\%b\\_c\\\\d'


class TestGetColumn:
    def test_valid(self):
        assert _get_column(SampleModel, 'name') is not None

    def test_invalid(self):
        with pytest.raises(BadRequestError, match='不支持的查询字段'):
            _get_column(SampleModel, 'nonexistent')


class TestConvertValue:
    def test_bool_true(self):
        assert _convert_value(bool, 'true') is True
        assert _convert_value(bool, '1') is True

    def test_bool_false(self):
        assert _convert_value(bool, 'false') is False

    def test_int(self):
        assert _convert_value(int, '42') == 42

    def test_str(self):
        assert _convert_value(str, 'hello') == 'hello'

    def test_datetime(self):
        dt = _convert_value(datetime, '2026-01-15T10:30:00')
        assert isinstance(dt, datetime)

    def test_invalid_returns_raw(self):
        assert _convert_value(int, 'not_a_number') == 'not_a_number'


class TestParseLookup:
    def test_single(self):
        assert parse_lookup('name==alice', SampleModel, {'name'}) is not None

    def test_multiple_and(self):
        assert parse_lookup('name==alice;age==30', SampleModel, {'name', 'age'}) is not None

    def test_field_not_in_whitelist(self):
        with pytest.raises(BadRequestError, match='lookup 仅支持字段'):
            parse_lookup('age==30', SampleModel, {'name'})

    def test_duplicate_field(self):
        with pytest.raises(BadRequestError, match='lookup 不可重复指定字段'):
            parse_lookup('name==alice;name==bob', SampleModel, {'name'})

    def test_empty_value(self):
        with pytest.raises(BadRequestError, match='value 不能为空'):
            parse_lookup('name==', SampleModel, {'name'})

    def test_empty_input(self):
        with pytest.raises(BadRequestError, match='至少需要一个有效查询条件'):
            parse_lookup('', SampleModel, {'name'})

    def test_bad_format(self):
        with pytest.raises(BadRequestError, match='key==value'):
            parse_lookup('name=alice', SampleModel, {'name'})

    def test_whitespace_stripped(self):
        assert parse_lookup(' name == alice ', SampleModel, {'name'}) is not None

    def test_only_semicolons(self):
        with pytest.raises(BadRequestError, match='至少需要一个有效查询条件'):
            parse_lookup(';;;', SampleModel, {'name'})


class TestParseWhere:
    def test_eq(self):
        assert parse_where('name==alice', SampleModel) is not None

    def test_ne(self):
        assert parse_where('name!=alice', SampleModel) is not None

    def test_ilike(self):
        assert parse_where('name~=ali', SampleModel) is not None

    def test_gt(self):
        assert parse_where('age>18', SampleModel) is not None

    def test_gte(self):
        assert parse_where('age>=18', SampleModel) is not None

    def test_lt(self):
        assert parse_where('age<60', SampleModel) is not None

    def test_lte(self):
        assert parse_where('age<=60', SampleModel) is not None

    def test_between(self):
        assert parse_where('age~18~60', SampleModel) is not None

    def test_between_bad_format(self):
        with pytest.raises(BadRequestError, match='between 格式错误'):
            parse_where('age~18', SampleModel)

    def test_and_semicolon(self):
        assert parse_where('name==alice;age>18', SampleModel) is not None

    def test_or_comma(self):
        assert parse_where('name==alice,name==bob', SampleModel) is not None

    def test_parentheses(self):
        assert parse_where('(name==alice,name==bob);age>18', SampleModel) is not None

    def test_nested_parentheses(self):
        assert parse_where('((name==alice,name==bob);age>18),is_active==true', SampleModel) is not None

    def test_missing_closing_paren(self):
        with pytest.raises(BadRequestError, match='缺少右括号'):
            parse_where('(name==alice', SampleModel)

    def test_missing_field(self):
        with pytest.raises(BadRequestError, match='缺少字段名'):
            parse_where('==alice', SampleModel)

    def test_missing_operator(self):
        with pytest.raises(BadRequestError, match='缺少操作符'):
            parse_where('namealice', SampleModel)

    def test_empty_value(self):
        with pytest.raises(BadRequestError, match='value 不能为空'):
            parse_where('name==', SampleModel)

    def test_extra_chars(self):
        with pytest.raises(BadRequestError, match='多余字符'):
            parse_where('name==alice)', SampleModel)

    def test_nonexistent_field(self):
        with pytest.raises(BadRequestError, match='不支持的查询字段'):
            parse_where('badfield==x', SampleModel)

    def test_complex(self):
        assert parse_where('(name~=张,age~20~30);is_active!=false', SampleModel) is not None


class TestParseKeyword:
    def test_single_field(self):
        assert parse_keyword('alice', 'name', SampleModel) is not None

    def test_multiple_fields(self):
        assert parse_keyword('alice', 'name,is_active', SampleModel) is not None

    def test_empty_q_field(self):
        assert parse_keyword('alice', '', SampleModel) is None

    def test_whitespace_q_field(self):
        assert parse_keyword('alice', ' , , ', SampleModel) is None

    def test_nonexistent_field(self):
        with pytest.raises(BadRequestError, match='不支持的查询字段'):
            parse_keyword('alice', 'bad_field', SampleModel)


class TestParseSort:
    def test_single_asc(self):
        assert len(parse_sort('name', SampleModel)) == 1

    def test_single_desc(self):
        assert len(parse_sort('-created_at', SampleModel)) == 1

    def test_multiple(self):
        assert len(parse_sort('-created_at,name', SampleModel)) == 2

    def test_empty(self):
        assert len(parse_sort('', SampleModel)) == 0

    def test_whitespace_only(self):
        assert len(parse_sort(' , , ', SampleModel)) == 0

    def test_nonexistent_field(self):
        with pytest.raises(BadRequestError, match='不支持的查询字段'):
            parse_sort('bad_field', SampleModel)


class TestBuildQueryExpressions:
    def test_where_only(self):
        exprs, order = build_query_expressions(SampleModel, where='name==alice')
        assert len(exprs) == 1 and len(order) == 0

    def test_keyword_only(self):
        exprs, order = build_query_expressions(SampleModel, q='alice', q_field='name')
        assert len(exprs) == 1 and len(order) == 0

    def test_sort_only(self):
        exprs, order = build_query_expressions(SampleModel, sort='-created_at,name')
        assert len(exprs) == 0 and len(order) == 2

    def test_combined(self):
        exprs, order = build_query_expressions(
            SampleModel, where='age>18', q='alice', q_field='name', sort='-created_at',
        )
        assert len(exprs) == 2 and len(order) == 1

    def test_all_none(self):
        exprs, order = build_query_expressions(SampleModel)
        assert len(exprs) == 0 and len(order) == 0

    def test_q_without_q_field(self):
        exprs, _ = build_query_expressions(SampleModel, q='alice')
        assert len(exprs) == 0

    def test_invalid_where_raises(self):
        with pytest.raises(BadRequestError):
            build_query_expressions(SampleModel, where='badfield==x')
