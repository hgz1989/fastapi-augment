"""
logger 模块测试 — factory / filters / handlers / config
"""
# ruff: noqa: DTZ001  # 轮转测试用 naive 本地时刻模拟固定时间点，与 handler 内部语义一致
import logging
from datetime import datetime

import pytest

from fastapi_augment.logger import (
    UvicornNameRewriteFilter,
    MonthlyRotatingFileHandler,
    YearlyRotatingFileHandler,
    MultiProcessTimedRotatingFileHandler,
    set_log_level,
    set_log_format,
    setup_logger
)
from fastapi_augment.logger.record_factory import (
    install_request_id_factory,
    _record_factory
)
from fastapi_augment.middlewares.request_id import (
    request_id_ctx_var
)


# ── factory: request_id 注入 ─────────────────────────────────────────

class TestRequestIdFactory:

    def test_install_factory(self):
        """install_request_id_factory 安装后，日志记录自动携带 request_id"""
        install_request_id_factory()
        factory = logging.getLogRecordFactory()
        record = factory('test', logging.INFO, '', 0, 'msg', (), None)
        assert hasattr(record, 'request_id')

    def test_request_id_default_dash(self):
        """无请求上下文时 request_id 为 '-'"""
        # 确保 ContextVar 处于默认值
        token = request_id_ctx_var.set(None)
        try:
            record = _record_factory('test', logging.INFO, '', 0, 'msg', (), None)
            assert record.request_id == '-'
        finally:
            request_id_ctx_var.reset(token)

    def test_request_id_injected(self):
        """设置 ContextVar 后，日志记录注入对应 request_id"""
        token = request_id_ctx_var.set('req-abc-123')
        try:
            record = _record_factory('test', logging.INFO, '', 0, 'msg', (), None)
            assert record.request_id == 'req-abc-123'
        finally:
            request_id_ctx_var.reset(token)

    def test_request_id_empty_string_becomes_dash(self):
        """ContextVar 为空字符串时，request_id 回退为 '-'"""
        token = request_id_ctx_var.set('')
        try:
            record = _record_factory('test', logging.INFO, '', 0, 'msg', (), None)
            assert record.request_id == '-'
        finally:
            request_id_ctx_var.reset(token)


# ── filters: UvicornNameRewriteFilter ────────────────────────────────

class TestUvicornNameRewriteFilter:

    def test_rewrite_uvicorn_error(self):
        """uvicorn.error 名称被重写为 uvicorn"""
        f = UvicornNameRewriteFilter()
        record = logging.LogRecord('uvicorn.error', logging.INFO, '', 0, 'msg', (), None)
        assert f.filter(record) is True
        assert record.name == 'uvicorn'

    def test_rewrite_uvicorn_access(self):
        """uvicorn.access 名称被重写为 uvicorn"""
        f = UvicornNameRewriteFilter()
        record = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, 'msg', (), None)
        assert f.filter(record) is True
        assert record.name == 'uvicorn'

    def test_no_rewrite_other_loggers(self):
        """非 uvicorn 的日志名称不被修改"""
        f = UvicornNameRewriteFilter()
        record = logging.LogRecord('myapp.views', logging.INFO, '', 0, 'msg', (), None)
        assert f.filter(record) is True
        assert record.name == 'myapp.views'

    def test_no_rewrite_bare_uvicorn(self):
        """已经是 'uvicorn' 的名称不被修改"""
        f = UvicornNameRewriteFilter()
        record = logging.LogRecord('uvicorn', logging.INFO, '', 0, 'msg', (), None)
        assert f.filter(record) is True
        assert record.name == 'uvicorn'


# ── handlers: 月/年轮转计算 ──────────────────────────────────────────

class TestMonthlyRotatingFileHandler:

    def test_compute_rollover_normal_month(self, tmp_path):
        """普通月份：下次轮转为下月1日00:00:00"""
        handler = MonthlyRotatingFileHandler(str(tmp_path / 'test.logger'))
        try:
            # 2026-03-15 12:00:00
            current = datetime(2026, 3, 15, 12, 0, 0).timestamp()
            rollover = handler.computeRollover(current)
            expected = datetime(2026, 4, 1, 0, 0, 0).timestamp()
            assert rollover == expected
        finally:
            handler.close()

    def test_compute_rollover_december(self, tmp_path):
        """12月：下次轮转为下一年1月1日"""
        handler = MonthlyRotatingFileHandler(str(tmp_path / 'test.logger'))
        try:
            current = datetime(2026, 12, 20, 10, 0, 0).timestamp()
            rollover = handler.computeRollover(current)
            expected = datetime(2027, 1, 1, 0, 0, 0).timestamp()
            assert rollover == expected
        finally:
            handler.close()

    def test_compute_rollover_on_first_day(self, tmp_path):
        """当月1日当天：下次轮转为下月1日"""
        handler = MonthlyRotatingFileHandler(str(tmp_path / 'test.logger'))
        try:
            current = datetime(2026, 6, 1, 0, 0, 0).timestamp()
            rollover = handler.computeRollover(current)
            expected = datetime(2026, 7, 1, 0, 0, 0).timestamp()
            assert rollover == expected
        finally:
            handler.close()


class TestYearlyRotatingFileHandler:

    def test_compute_rollover_mid_year(self, tmp_path):
        """年中：下次轮转为下一年1月1日"""
        handler = YearlyRotatingFileHandler(str(tmp_path / 'test.logger'))
        try:
            current = datetime(2026, 7, 15, 12, 0, 0).timestamp()
            rollover = handler.computeRollover(current)
            expected = datetime(2027, 1, 1, 0, 0, 0).timestamp()
            assert rollover == expected
        finally:
            handler.close()

    def test_compute_rollover_jan_first(self, tmp_path):
        """1月1日当天：下次轮转仍为下一年1月1日"""
        handler = YearlyRotatingFileHandler(str(tmp_path / 'test.logger'))
        try:
            current = datetime(2026, 1, 1, 0, 0, 0).timestamp()
            rollover = handler.computeRollover(current)
            expected = datetime(2027, 1, 1, 0, 0, 0).timestamp()
            assert rollover == expected
        finally:
            handler.close()

    def test_compute_rollover_dec_31(self, tmp_path):
        """12月31日：下次轮转为次日（下一年1月1日）"""
        handler = YearlyRotatingFileHandler(str(tmp_path / 'test.logger'))
        try:
            current = datetime(2026, 12, 31, 23, 59, 59).timestamp()
            rollover = handler.computeRollover(current)
            expected = datetime(2027, 1, 1, 0, 0, 0).timestamp()
            assert rollover == expected
        finally:
            handler.close()


class TestMultiProcessTimedRotatingFileHandler:

    def test_do_rollover_permission_error(self, tmp_path):
        """doRollover 遇到 PermissionError 时不抛出，重新打开文件流"""
        log_file = tmp_path / 'test.logger'
        log_file.write_text('old content')
        handler = MultiProcessTimedRotatingFileHandler(
            str(log_file), when='midnight', backupCount=3
        )
        try:
            # 模拟 super().doRollover() 抛出 PermissionError
            original = logging.handlers.TimedRotatingFileHandler.doRollover

            def mock_rollover(self_handler):
                raise PermissionError('simulated')

            logging.handlers.TimedRotatingFileHandler.doRollover = mock_rollover
            # 不应抛出异常
            handler.doRollover()
            # stream 应被重新打开
            assert handler.stream is not None
        finally:
            logging.handlers.TimedRotatingFileHandler.doRollover = original
            handler.close()


# ── config: set_log_level / set_log_format / setup_logger ────────────

class TestSetLogLevel:

    def test_set_level_string(self):
        """字符串级别设置"""
        set_log_level('WARNING')
        assert logging.getLogger().level == logging.WARNING

    def test_set_level_int(self):
        """整数级别设置"""
        set_log_level(logging.ERROR)
        assert logging.getLogger().level == logging.ERROR

    def test_set_level_case_insensitive(self):
        """字符串不区分大小写"""
        set_log_level('debug')
        assert logging.getLogger().level == logging.DEBUG

    def test_set_level_invalid_defaults_to_info(self):
        """无效字符串回退到 INFO"""
        set_log_level('nonexistent')
        assert logging.getLogger().level == logging.INFO


class TestSetLogFormat:

    def test_set_format_updates_all_handlers(self):
        """set_log_format 更新所有处理器的 formatter"""
        root = logging.getLogger()
        new_fmt = '%(message)s'
        set_log_format(new_fmt)
        for handler in root.handlers:
            if handler.formatter:
                assert handler.formatter._fmt == new_fmt


class TestSetupLogger:

    def test_setup_with_file_handler_day(self, tmp_path):
        """setup_logger 创建按天轮转的文件处理器"""
        root = logging.getLogger()
        before_count = len([h for h in root.handlers if isinstance(h, logging.FileHandler)])

        setup_logger(log_dir=str(tmp_path), filename='test.logger', rotation='day')

        after_count = len([h for h in root.handlers if isinstance(h, logging.FileHandler)])
        assert after_count == before_count + 1

        # 清理
        for h in root.handlers[:]:
            if isinstance(h, logging.FileHandler) and 'test.logger' in getattr(h, 'baseFilename', ''):
                h.close()
                root.removeHandler(h)

    def test_setup_with_month_rotation(self, tmp_path):
        """setup_logger 使用 month 轮转创建 MonthlyRotatingFileHandler"""
        root = logging.getLogger()
        setup_logger(log_dir=str(tmp_path), filename='monthly.logger', rotation='month')

        monthly_handlers = [
            h for h in root.handlers
            if isinstance(h, MonthlyRotatingFileHandler)
        ]
        assert len(monthly_handlers) >= 1

        # 清理
        for h in root.handlers[:]:
            if isinstance(h, logging.FileHandler) and 'monthly.logger' in getattr(h, 'baseFilename', ''):
                h.close()
                root.removeHandler(h)

    def test_setup_with_year_rotation(self, tmp_path):
        """setup_logger 使用 year 轮转创建 YearlyRotatingFileHandler"""
        root = logging.getLogger()
        setup_logger(log_dir=str(tmp_path), filename='yearly.logger', rotation='year')

        yearly_handlers = [
            h for h in root.handlers
            if isinstance(h, YearlyRotatingFileHandler)
        ]
        assert len(yearly_handlers) >= 1

        # 清理
        for h in root.handlers[:]:
            if isinstance(h, logging.FileHandler) and 'yearly.logger' in getattr(h, 'baseFilename', ''):
                h.close()
                root.removeHandler(h)

    def test_setup_invalid_rotation_raises(self, tmp_path):
        """无效轮转粒度抛出 ValueError"""
        with pytest.raises(ValueError, match='不支持的轮转粒度'):
            setup_logger(log_dir=str(tmp_path), rotation='invalid')

    def test_setup_no_log_dir_no_file_handler(self):
        """不提供 log_dir 时不创建文件处理器"""
        root = logging.getLogger()
        before = len([h for h in root.handlers if isinstance(h, logging.FileHandler)])
        setup_logger(log_dir=None)
        after = len([h for h in root.handlers if isinstance(h, logging.FileHandler)])
        assert after == before

    def test_setup_idempotent_same_path(self, tmp_path):
        """相同路径重复调用不重复添加处理器"""
        root = logging.getLogger()
        setup_logger(log_dir=str(tmp_path), filename='dup.logger')
        count_after_first = len([
            h for h in root.handlers
            if isinstance(h, logging.FileHandler) and 'dup.logger' in getattr(h, 'baseFilename', '')
        ])

        setup_logger(log_dir=str(tmp_path), filename='dup.logger')
        count_after_second = len([
            h for h in root.handlers
            if isinstance(h, logging.FileHandler) and 'dup.logger' in getattr(h, 'baseFilename', '')
        ])
        assert count_after_first == count_after_second

        # 清理
        for h in root.handlers[:]:
            if isinstance(h, logging.FileHandler) and 'dup.logger' in getattr(h, 'baseFilename', ''):
                h.close()
                root.removeHandler(h)

    def test_setup_disable_console(self, tmp_path):
        """enable_console=False 移除控制台 StreamHandler"""
        root = logging.getLogger()
        # 先确保有控制台处理器
        setup_logger(enable_console=True)

        console_before = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(console_before) > 0

        setup_logger(enable_console=False)

        console_after = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(console_after) == 0

        # 恢复控制台（避免影响后续测试）
        setup_logger(enable_console=True)
