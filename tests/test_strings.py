"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 字符串工具函数测试——命名转换、随机串、JSON 序列化
"""
import io
import json
import string

import pytest

from fastapi_augment.common.utils.strings import (
    camel_to_snake,
    json_dump,
    json_dumps,
    json_load,
    json_loads,
    random_string,
    snake_to_camel,
)


class TestCamelToSnake:

    def test_basic(self):
        """常规驼峰转换"""
        assert camel_to_snake('userName') == 'user_name'

    def test_consecutive_upper(self):
        """连续大写转换（如 HTTPRequest）"""
        assert camel_to_snake('HTTPRequest') == 'http_request'

    def test_empty_string(self):
        """空串原样返回"""
        assert camel_to_snake('') == ''

    def test_single_letter(self):
        """单个大写字母"""
        assert camel_to_snake('A') == 'a'

    def test_mixed_underscore_kept(self):
        """已含下划线时保持原下划线"""
        assert camel_to_snake('user_name') == 'user_name'

    def test_digit_boundary(self):
        """大写字母后紧跟数字的情况"""
        assert camel_to_snake('item2Id') == 'item2_id'


class TestSnakeToCamel:

    def test_basic(self):
        """下划线转驼峰（首字母大写）"""
        assert snake_to_camel('hello_world') == 'HelloWorld'

    def test_empty_string(self):
        """空串原样返回"""
        assert snake_to_camel('') == ''

    def test_single_word(self):
        """单段单词首字母大写"""
        assert snake_to_camel('user') == 'User'


class TestRandomString:

    def test_default_length(self):
        """默认长度 16，字符集为字母+数字"""
        s = random_string()
        assert len(s) == 16
        assert all(c in (string.ascii_letters + string.digits) for c in s)

    def test_custom_length_and_chars(self):
        """自定义长度与字符集"""
        s = random_string(length=8, chars='abc')
        assert len(s) == 8
        assert set(s) <= {'a', 'b', 'c'}

    def test_exclude_chars(self):
        """exclude 排除指定字符"""
        s = random_string(length=10, chars='abc', exclude='a')
        assert 'a' not in s

    def test_zero_length_raises(self):
        """length < 1 时抛出 ValueError"""
        with pytest.raises(ValueError, match='length 必须为正整数'):
            random_string(length=0)

    def test_empty_charset_raises(self):
        """exclude 排空字符集时抛出 ValueError"""
        with pytest.raises(ValueError, match='字符集为空'):
            random_string(length=5, chars='ab', exclude='ab')


class TestJsonDumps:

    def test_compact(self):
        """压缩输出"""
        assert json_dumps({'a': 1}) == '{"a":1}'

    def test_indent(self):
        """非压缩输出带缩进"""
        assert json_dumps({'a': 1}, compact=False) == '{\n  "a": 1\n}'

    def test_unicode_preserved(self):
        """中文不转义"""
        assert json_dumps({'msg': '你好'}) == '{"msg":"你好"}'

    def test_unserializable_raises(self, monkeypatch):
        """不可序列化对象抛 TypeError（orjson 与 fallback 分支消息不同，仅断言类型）"""
        monkeypatch.setattr('fastapi_augment.common.utils.strings.ORJSON_INSTALLED', False)
        with pytest.raises(TypeError):
            json_dumps(object())


class TestJsonLoads:

    def test_str(self):
        """字符串反序列化"""
        assert json_loads('{"a": 1}') == {'a': 1}

    def test_bytes(self):
        """字节反序列化"""
        assert json_loads(b'{"a": 1}') == {'a': 1}

    def test_invalid_raises(self):
        """非法 JSON 抛 JSONDecodeError"""
        with pytest.raises(json.JSONDecodeError):
            json_loads('not-json')


class TestJsonDumpLoad:

    def test_dump_then_load_roundtrip(self, tmp_path):
        """写入文件后可读回"""
        p = tmp_path / 'data.json'
        with open(p, 'w', encoding='utf-8') as fp:
            json_dump({'a': 1}, fp)
        with open(p, 'rb') as fp:
            assert json_load(fp) == {'a': 1}

    def test_load_invalid_raises(self, tmp_path):
        """读取非法 JSON 抛 JSONDecodeError"""
        p = tmp_path / 'bad.json'
        p.write_text('bad', encoding='utf-8')
        with open(p, 'rb') as fp, pytest.raises(json.JSONDecodeError):
            json_load(fp)

    def test_dump_compact_flag(self):
        """compact=False 写入缩进格式"""
        buf = io.StringIO()
        json_dump({'a': 1}, buf, compact=False)
        assert buf.getvalue() == '{\n  "a": 1\n}'
