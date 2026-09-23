"""
@Author         : hangu
@CreateDate     : 2026/9/4
@Description    : 字符串工具函数——命名转换、随机串、JSON 序列化
"""
import json
import random
import string
from typing import Protocol, Any


# ── 类型定义 ──
class SupportsWriteStr(Protocol):
    def write(self, s: str) -> object: ...


class SupportsReadBytes(Protocol):
    def read(self) -> bytes: ...


# ── orjson 可选加载 ──
ORJSON_INSTALLED: bool = False
ORJSON_DEFAULT_OPTS: int = 0
_oj_dumps: Any = None
_oj_loads: Any = None

try:
    import orjson as _orjson
    ORJSON_INSTALLED = True
    ORJSON_DEFAULT_OPTS = _orjson.OPT_SERIALIZE_NUMPY | _orjson.OPT_UTC_Z
    _oj_dumps = _orjson.dumps
    _oj_loads = _orjson.loads
except ImportError:
    pass


# orjson OPT_INDENT_2 的常量值（1），避免直接依赖 orjson 安装；
# 注意该值并非 0x04（0x04 是 OPT_NON_STR_KEYS），曾导致缩进不生效
_ORJSON_OPT_INDENT_2 = 0x01


# ── 字符串转换 ──
def camel_to_snake(s: str) -> str:
    """驼峰转下划线（支持连续大写）

    Returns:
        转换后的下划线命名字符串
    """
    if not s:
        return s
    result: list[str] = []
    prev_lower = False
    for i, c in enumerate(s):
        if c.isupper():
            if i > 0 and (prev_lower or (i + 1 < len(s) and s[i + 1].islower())):
                result.append('_')
            result.append(c.lower())
            prev_lower = False
        else:
            result.append(c)
            prev_lower = c.islower()
    return ''.join(result)


def snake_to_camel(s: str) -> str:
    """下划线转驼峰（首字母大写）

    Returns:
        转换后的驼峰命名字符串
    """
    if not s:
        return s
    return ''.join(part.capitalize() for part in s.split('_'))


# ── 随机字符串 ──
def random_string(
        length: int = 16,
        chars: str | None = None,
        exclude: str | None = None,
) -> str:
    """生成随机字符串，支持自定义字符集

    Returns:
        指定长度的随机字符串

    Raises:
        ValueError: length 非正整数或字符集为空时（exclude 排除了所有字符）
    """
    if length < 1:
        raise ValueError(f'length 必须为正整数，当前值: {length}')
    if chars is None:
        chars = string.ascii_letters + string.digits
    if exclude:
        chars = ''.join(c for c in chars if c not in exclude)
    if not chars:
        raise ValueError('字符集为空，无法生成随机字符串（exclude 排除了所有字符）')
    return ''.join(random.choices(chars, k=length))


# ── JSON 序列化 ──
def json_dumps(obj: Any, compact: bool = True) -> str:
    """高性能 JSON 序列化

    Args:
        obj: 要序列化的对象
        compact: 是否压缩输出（去除空格）

    Returns:
        JSON 字符串

    Raises:
        TypeError: 当对象不可序列化时
    """
    if ORJSON_INSTALLED:
        try:
            opts = ORJSON_DEFAULT_OPTS
            if not compact:
                opts |= _ORJSON_OPT_INDENT_2
            return _oj_dumps(obj, option=opts).decode('utf-8')
        except (TypeError, ValueError) as e:
            raise TypeError(f'JSON 序列化失败: {e}') from e
    if compact:
        return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    return json.dumps(obj, ensure_ascii=False, indent=2)


def json_dump(obj: Any, fp: SupportsWriteStr, compact: bool = True) -> None:
    """高性能 JSON 写入文件

    Args:
        obj: 要序列化的对象
        fp: 可写文件对象
        compact: 是否压缩输出
    """
    fp.write(json_dumps(obj, compact=compact))


def json_loads(s: str | bytes) -> Any:
    """高性能 JSON 反序列化

    Args:
        s: JSON 字符串或字节

    Returns:
        反序列化后的 Python 对象

    Raises:
        json.JSONDecodeError: JSON 解析失败时
    """
    if ORJSON_INSTALLED:
        try:
            return _oj_loads(s)
        except (TypeError, ValueError) as e:
            text = s.decode('utf-8', errors='replace') if isinstance(s, bytes) else s
            raise json.JSONDecodeError(str(e), text, 0) from e
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        raise
    except (TypeError, ValueError) as e:
        raise json.JSONDecodeError(str(e), s, 0) from e


def json_load(fp: SupportsReadBytes) -> Any:
    """从文件读取 JSON

    Args:
        fp: 可读字节文件对象

    Returns:
        反序列化后的 Python 对象

    Raises:
        json.JSONDecodeError: JSON 解析失败时
        OSError: 文件读取失败时
    """
    try:
        raw = fp.read()
    except OSError as e:
        raise OSError(f'文件读取失败: {e}') from e
    if ORJSON_INSTALLED:
        try:
            return _oj_loads(raw)
        except (TypeError, ValueError) as e:
            raise json.JSONDecodeError(str(e), raw.decode('utf-8', errors='replace'), 0) from e
    return json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else raw)
