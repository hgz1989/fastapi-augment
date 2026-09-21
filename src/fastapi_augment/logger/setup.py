"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 日志初始化与管理——日志格式、级别、轮转、控制台/文件输出
"""
import logging
import sys
from pathlib import Path

from .filters import UvicornNameRewriteFilter
from .handlers import (
    MonthlyRotatingFileHandler,
    YearlyRotatingFileHandler,
    MultiProcessTimedRotatingFileHandler
)
from .record_factory import (
    install_request_id_factory
)

# -------------------------------------
# 日志格式
# -------------------------------------
NORMAL_FORMAT = (
    '%(asctime)s.%(msecs)03d | %(levelname)s | %(process)d:%(thread)d | '
    '%(name)s | %(lineno)d | %(request_id)s | %(message)s'
)
_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 轮转周期映射：语义字符串 → (when, interval)，month/year 使用自定义Handler
_ROTATION_MAP: dict[str, tuple[str, int] | None] = {
    'second': ('S', 1),
    'minute': ('M', 1),
    'hour': ('H', 1),
    'day': ('midnight', 1),
    'week': ('W0', 1),
    'month': None,
    'year': None,
}

# 需要接管的日志名称（清空默认处理器，走根日志）
_TAKEOVER_LOGGERS = ('uvicorn', 'uvicorn.access', 'uvicorn.error', 'fastapi')


def _takeover_uvicorn() -> None:
    """强制接管uvicorn/fastapi日志：清空handler、propagate回根、附加名称重写过滤器"""
    for logger_name in _TAKEOVER_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.INFO)

        if logger_name in ('uvicorn.error', 'uvicorn.access'):
            logger.addFilter(UvicornNameRewriteFilter())


_init_done = False


def _init_root_logger() -> None:
    """初始化根日志：安装request_id工厂、设置格式、接管uvicorn

    仅在首次调用时执行，重复导入不会重复初始化
    根日志级别设为WARNING，第三方库的DEBUG/INFO默认不输出
    uvicorn/fastapi已单独设为INFO，不受根日志影响

    Note:
        basicConfig 不使用 force=True：若宿主应用已配置根日志 handler，
        本库不会强制覆盖，避免作为第三方库引入时破坏宿主日志配置；
        宿主未配置时才按本库默认格式初始化
        多进程环境下各进程拥有独立内存空间，_init_done 在每个
        子进程中独立为 False，每个进程各自完成一次初始化——这是
        符合预期的行为，日志 handler 属于进程级资源
        多线程安全由 Python 导入锁与 GIL 保证，无需额外同步
    """
    global _init_done
    if _init_done:
        return
    install_request_id_factory()
    logging.basicConfig(
        level=logging.WARNING,
        format=NORMAL_FORMAT,
        datefmt=_DATE_FORMAT,
    )
    _takeover_uvicorn()
    _init_done = True


# 包导入时自动执行一次初始化（幂等；宿主已配置根日志时不会覆盖其配置）
_init_root_logger()


# -------------------------------------
# 对外API
# -------------------------------------
def set_log_level(level: str | int, logger_name: str | None = None) -> None:
    """修改项目日志级别（不影响第三方库）

    Args:
        level: 支持传入 'debug' / 'info' / 'warn' / 'error' 或logging.DEBUG等
        logger_name: 项目logger名称，不传则仅修改根日志级别
    """
    if isinstance(level, str):
        level = level.upper()
        level = getattr(logging, level, logging.INFO)

    if logger_name:
        logging.getLogger(logger_name).setLevel(level)
    else:
        logging.getLogger().setLevel(level)


def set_log_format(log_format: str) -> None:
    """修改全局日志格式，所有输出立即生效

    Args:
        log_format: 新的日志格式字符串
    """
    root_logger = logging.getLogger()
    formatter = logging.Formatter(log_format)

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


def setup_logger(
    log_dir: str | Path | None = None,
    filename: str = 'app.logger',
    rotation: str = 'day',
    backup_count: int = 30,
    encoding: str = 'utf-8',
    enable_console: bool = True,
) -> None:
    """一键配置应用日志（支持控制台开关与文件日志）

    支持以整点为节点的日志轮转，可选粒度：
    - ``'second'`` — 每整秒
    - ``'minute'`` — 每整分钟（:00秒）
    - ``'hour'``   — 每整点小时（:00分）
    - ``'day'``    — 每天00:00（默认）
    - ``'week'``   — 每周一00:00
    - ``'month'``  — 每月1日00:00
    - ``'year'``   — 每年1月1日00:00

    Args:
        log_dir: 日志保存目录，若不提供则不开启文件日志
        filename: 日志文件名
        rotation: 轮转粒度，见上方说明，默认 ``'day'``
        backup_count: 保留的历史日志文件数量
        encoding: 文件编码
        enable_console: 是否在控制台输出日志
    """
    root_logger = logging.getLogger()

    # 1. 获取现有formatter
    current_formatter = None
    for h in root_logger.handlers:
        if h.formatter:
            current_formatter = h.formatter
            break

    if not current_formatter:
        current_formatter = logging.Formatter(NORMAL_FORMAT, datefmt=_DATE_FORMAT)

    # 2. 控制台输出
    if enable_console:
        has_console = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in root_logger.handlers
        )
        if not has_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(current_formatter)
            root_logger.addHandler(console_handler)
    else:
        handlers_to_remove = [
            h for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        for h in handlers_to_remove:
            root_logger.removeHandler(h)

    # 3. 文件输出
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / filename

        has_file_handler = any(
            isinstance(h, logging.FileHandler)
            and getattr(h, 'baseFilename', '') == str(file_path.absolute())
            for h in root_logger.handlers
        )

        if not has_file_handler:
            rotation_key = rotation.lower()

            if rotation_key not in _ROTATION_MAP:
                raise ValueError(
                    f'不支持的轮转粒度 {rotation!r}，'
                    f'可选值：{list(_ROTATION_MAP.keys())}'
                )

            if rotation_key == 'month':
                file_handler = MonthlyRotatingFileHandler(
                    str(file_path), backup_count=backup_count, encoding=encoding
                )
            elif rotation_key == 'year':
                file_handler = YearlyRotatingFileHandler(
                    str(file_path), backup_count=backup_count, encoding=encoding
                )
            else:
                rotation_entry = _ROTATION_MAP[rotation_key]
                assert rotation_entry is not None  # month/year 已在上层处理
                when, interval = rotation_entry
                file_handler = MultiProcessTimedRotatingFileHandler(
                    filename=str(file_path), when=when, interval=interval,
                    backupCount=backup_count, encoding=encoding
                )

            file_handler.setFormatter(current_formatter)
            root_logger.addHandler(file_handler)
