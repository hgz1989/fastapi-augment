"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 应用入口——模块级配置日志（主进程与 reload/多 worker 子进程一致），启动时校验 ASGI 导入并启动 Uvicorn
"""
from fastapi_augment.common import validate_asgi_import
from fastapi_augment.logger import setup_logger, set_log_level

from config import project_settings, settings, uvicorn_settings


def _configure_logging() -> None:
    """配置日志（模块级执行）

    放在模块级而非 __main__ 块的原因：uvicorn 的 reload / 多 worker 子进程
    （Windows spawn）会重新导入 main.py，但不会执行 __main__ 块；模块级
    执行保证主进程与每个子进程的日志配置一致（文件/控制台行为相同）。
    setup_logger 内部幂等（重复调用不重复添加 handler）。
    """
    if project_settings.debug:
        # 调试模式：DEBUG 级别、不写文件（仅控制台）
        set_log_level('DEBUG')
        setup_logger()
    else:
        set_log_level(settings.logs_level)
        setup_logger(
            log_dir=settings.logs_dir,
            filename=settings.logs_filename,
            rotation=settings.logs_rotation,
            backup_count=settings.logs_backup_count,
            encoding=settings.logs_encoding,
            enable_console=settings.logs_enable_console,
        )


# 模块级执行：主进程与 reload/多 worker 子进程（spawn 重导入）都会执行
_configure_logging()

if __name__ == '__main__':
    import uvicorn

    # 校验配置的 ASGI 应用（apps.api:app）真实存在且可调用
    validate_asgi_import(uvicorn_settings.asgi_app_ref)

    # 启动服务
    uvicorn.run(
        uvicorn_settings.asgi_app_ref,
        host=uvicorn_settings.host,
        port=uvicorn_settings.port,
        reload=uvicorn_settings.reload,
        workers=uvicorn_settings.workers,
        access_log=uvicorn_settings.access_log,
        root_path=uvicorn_settings.root_path,
        log_config=None,
        server_header=False
    )
