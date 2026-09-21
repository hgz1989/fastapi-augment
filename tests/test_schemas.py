"""
schemas 模块测试 — 基类 / 分页 / 请求参数 / 响应模型
"""
from datetime import datetime, UTC, date

import pytest
from pydantic import ValidationError

from fastapi_augment.schemas.base import (
    ORMSchemaBase,
    SchemaBase
)
from fastapi_augment.schemas.pagination import (
    PageData
)
from fastapi_augment.schemas.request import (
    PageParams,
    TimeRangeParams,
    KeywordParams
)
from fastapi_augment.schemas.response import (
    APIResponse,
    CODE_SUCCESS,
    response_success,
    response_fail,
    build_response
)


# ── ORMSchemaBase ─────────────────────────────────────────────────────

class TestORMSchemaBase:

    def test_camel_case_alias(self):
        class MySchema(ORMSchemaBase):
            user_name: str = ''
            created_at: datetime | None = None

        # 通过驼峰别名构造
        obj = MySchema(userName='alice')
        assert obj.user_name == 'alice'

    def test_from_attributes(self):
        class MySchema(ORMSchemaBase):
            name: str = ''

        class FakeORM:
            name = 'bob'

        obj = MySchema.model_validate(FakeORM())
        assert obj.name == 'bob'

    def test_extra_fields_ignored(self):
        class MySchema(ORMSchemaBase):
            name: str = ''

        obj = MySchema(name='alice', extra_field='ignored')
        assert not hasattr(obj, 'extra_field')

    def test_datetime_json_encoder(self):
        class MySchema(ORMSchemaBase):
            ts: datetime

        dt = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
        obj = MySchema(ts=dt)
        json_str = obj.model_dump_json()
        assert '2026-09-04T12:00:00' in json_str

    def test_date_json_encoder(self):
        class MySchema(ORMSchemaBase):
            d: date

        obj = MySchema(d=date(2026, 9, 4))
        json_str = obj.model_dump_json()
        assert '2026-09-04' in json_str


# ── APISchemaBase ─────────────────────────────────────────────────────

class TestAPISchemaBase:

    def test_no_from_attributes(self):
        """APISchemaBase 关闭了 from_attributes"""
        config = SchemaBase.model_config
        assert config.get('from_attributes', False) is False

    def test_camel_case_alias(self):
        class MyOutput(SchemaBase):
            item_name: str = ''

        obj = MyOutput(itemName='test')
        assert obj.item_name == 'test'


# ── PageParams ────────────────────────────────────────────────────────

class TestPageParams:

    def test_defaults(self):
        p = PageParams()
        assert p.page == 1
        assert p.size == 100

    def test_custom_values(self):
        p = PageParams(page=3, size=50)
        assert p.page == 3
        assert p.size == 50

    def test_page_min_1(self):
        with pytest.raises(ValidationError):
            PageParams(page=0)

    def test_size_min_1(self):
        with pytest.raises(ValidationError):
            PageParams(size=0)

    def test_size_max_1000(self):
        with pytest.raises(ValidationError):
            PageParams(size=1001)

    def test_camel_case_input(self):
        p = PageParams(page=2, size=20)
        assert p.page == 2


# ── TimeRangeParams ───────────────────────────────────────────────────

class TestTimeRangeParams:

    def test_defaults_none(self):
        p = TimeRangeParams()
        assert p.start_time is None
        assert p.end_time is None

    def test_with_values(self):
        now = datetime.now(UTC)
        p = TimeRangeParams(start_time=now, end_time=now)
        assert p.start_time == now


# ── KeywordParams ─────────────────────────────────────────────────────

class TestKeywordParams:

    def test_default_none(self):
        p = KeywordParams()
        assert p.keyword is None

    def test_with_keyword(self):
        p = KeywordParams(keyword='search')
        assert p.keyword == 'search'

    def test_max_length_100(self):
        with pytest.raises(ValidationError):
            KeywordParams(keyword='x' * 101)


# ── PageData ──────────────────────────────────────────────────────────

class TestPageData:

    def test_build_basic(self):
        page = PageData.build(['a', 'b', 'c'], page=1, size=10, total=25)
        assert page.items == ['a', 'b', 'c']
        assert page.page == 1
        assert page.size == 10
        assert page.total == 25
        assert page.pages == 3  # ceil(25/10)

    def test_build_exact_page(self):
        page = PageData.build(['a'] * 10, page=1, size=10, total=10)
        assert page.pages == 1

    def test_build_empty(self):
        page = PageData.build([], page=1, size=10, total=0)
        assert page.items == []
        assert page.pages == 0
        assert page.total == 0

    def test_build_zero_size(self):
        page = PageData.build([], page=1, size=0, total=0)
        assert page.pages == 0

    def test_default_values(self):
        page = PageData()
        assert page.items == []
        assert page.page == 1
        assert page.size == 10
        assert page.pages == 0
        assert page.total == 0

    def test_camel_case_serialization(self):
        page = PageData.build(['x'], page=1, size=10, total=1)
        data = page.model_dump(by_alias=True)
        assert 'items' in data
        assert 'page' in data


# ── APIResponse ───────────────────────────────────────────────────────

class TestAPIResponse:

    def test_default_success(self):
        resp = APIResponse()
        assert resp.code == CODE_SUCCESS
        assert resp.message == '操作成功'
        assert resp.data is None
        assert resp.extra is None

    def test_with_data(self):
        resp = APIResponse(data={'name': 'alice'})
        assert resp.data == {'name': 'alice'}

    def test_with_extra(self):
        resp = APIResponse(extra={'total': 100})
        assert resp.extra == {'total': 100}


# ── response_success ──────────────────────────────────────────────────

class TestResponseSuccess:

    def test_basic(self):
        resp = response_success()
        assert resp.code == CODE_SUCCESS
        assert resp.message == '操作成功'
        assert resp.data is None

    def test_with_data(self):
        resp = response_success(data=[1, 2, 3])
        assert resp.data == [1, 2, 3]

    def test_with_message(self):
        resp = response_success(message='创建成功')
        assert resp.message == '创建成功'

    def test_with_data_and_extra(self):
        resp = response_success(data='ok', extra={'count': 1})
        assert resp.data == 'ok'
        assert resp.extra == {'count': 1}


# ── response_fail ─────────────────────────────────────────────────────

class TestResponseFail:

    def test_basic(self):
        resp = response_fail(code=1001)
        assert resp.code == 1001
        assert resp.message == '操作失败'
        assert resp.data is None

    def test_with_message(self):
        resp = response_fail(code=2000, message='余额不足')
        assert resp.code == 2000
        assert resp.message == '余额不足'

    def test_with_extra(self):
        resp = response_fail(code=1, extra={'retry': True})
        assert resp.extra == {'retry': True}


# ── build_response ────────────────────────────────────────────────────

class TestBuildResponse:

    def test_default(self):
        resp = build_response()
        assert resp.code == CODE_SUCCESS
        assert resp.data is None

    def test_full(self):
        resp = build_response(code=0, message='ok', data='d', extra='e')
        assert resp.code == 0
        assert resp.message == 'ok'
        assert resp.data == 'd'
        assert resp.extra == 'e'
