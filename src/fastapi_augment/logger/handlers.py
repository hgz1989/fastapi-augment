"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 多进程安全的日志轮转处理器，支持秒/分/时/天/周及自定义月/年轮转
"""
import logging
from datetime import UTC, datetime
from logging.handlers import (
    TimedRotatingFileHandler
)

_logger = logging.getLogger(__name__)


class MultiProcessTimedRotatingFileHandler(TimedRotatingFileHandler):
    """支持多进程安全的按时间轮转处理器

    多进程场景下，多个 worker 可能同时触发轮转
    通过捕获 ``OSError``（含 ``PermissionError``、``FileNotFoundError``）
    来兼容其他进程已完成轮转或删除了旧文件的情况
    """

    def doRollover(self) -> None:
        """执行轮转，捕获多进程竞争引发的文件系统异常"""
        try:
            super().doRollover()
        except OSError:
            # 其他进程已完成轮转或文件已被移动/删除，重新打开新文件流
            if self.stream:
                self.stream.close()
                self.stream = None
            try:
                self.stream = self._open()
            except OSError as exc:
                _logger.warning('Failed to reopen logger file after rollover: %s', exc)


class MonthlyRotatingFileHandler(MultiProcessTimedRotatingFileHandler):
    """按月轮转的日志处理器，以每月1日00:00:00为节点"""

    def __init__(self, filename: str, backup_count: int = 12, encoding: str = 'utf-8'):
        """初始化按月轮转处理器

        Args:
            filename: 日志文件路径
            backup_count: 保留的日志文件数量
            encoding: 文件编码
        """
        super().__init__(filename, when='midnight', backupCount=backup_count, encoding=encoding)

    def computeRollover(self, currentTime: int) -> int:
        """计算下次轮转时间（下月1日00:00:00）

        使用带时区的时间计算，避免轮转节点依赖服务器本地时区设置

        Args:
            currentTime: 当前UNIX时间戳

        Returns:
            下次轮转的UNIX时间戳
        """
        dt = datetime.fromtimestamp(currentTime, tz=UTC).astimezone()

        if dt.month == 12:
            next_month = datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
        else:
            next_month = datetime(dt.year, dt.month + 1, 1, tzinfo=dt.tzinfo)

        return int(next_month.timestamp())


class YearlyRotatingFileHandler(MultiProcessTimedRotatingFileHandler):
    """按年轮转的日志处理器，以每年1月1日00:00:00为节点"""

    def __init__(self, filename: str, backup_count: int = 5, encoding: str = 'utf-8'):
        """初始化按年轮转处理器

        Args:
            filename: 日志文件路径
            backup_count: 保留的日志文件数量
            encoding: 文件编码
        """
        super().__init__(filename, when='midnight', backupCount=backup_count, encoding=encoding)

    def computeRollover(self, currentTime: int) -> int:
        """计算下次轮转时间（下一年1月1日00:00:00）

        使用带时区的时间计算，避免轮转节点依赖服务器本地时区设置

        Args:
            currentTime: 当前UNIX时间戳

        Returns:
            下次轮转的UNIX时间戳
        """
        dt = datetime.fromtimestamp(currentTime, tz=UTC).astimezone()
        next_year = datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
        return int(next_year.timestamp())
