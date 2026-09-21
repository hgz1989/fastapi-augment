"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 自定义日志记录工厂，注入request_id到每条日志
"""
import logging
from typing import Any

from ..middlewares.request_id import (
    request_id_ctx_var
)

# 保存原始工厂
_old_factory = logging.getLogRecordFactory()


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """自定义日志记录工厂，在每条日志记录上注入当前请求的request_id

    Args:
        *args: 传递给原始工厂的位置参数
        **kwargs: 传递给原始工厂的关键字参数

    Returns:
        注入了request_id属性的日志记录对象
    """
    record = _old_factory(*args, **kwargs)
    record.request_id = request_id_ctx_var.get() or '-'
    return record


def install_request_id_factory() -> None:
    """安装自定义日志记录工厂，使所有日志自动携带request_id

    幂等操作：重复调用不会叠加包装层
    """
    if logging.getLogRecordFactory() is _record_factory:
        return
    global _old_factory
    _old_factory = logging.getLogRecordFactory()
    logging.setLogRecordFactory(_record_factory)
