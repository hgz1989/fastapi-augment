"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 全局配置——继承 fastapi_augment 的 AugmentBaseSettings，从根目录 .env 与环境变量加载
"""
from pathlib import Path

from fastapi_augment.common.utils import find_project_root, get_root_dir
from fastapi_augment.config import AugmentBaseSettings, DatabaseSettings
from pydantic import Field

# 常量
# 版本号唯一源：pyproject [tool.hatch.version] 从这里解析字面量（hatch 默认正则 (?i)^(__version__|VERSION)... 两者皆可）
VERSION = '0.1.0'
ENV_PREFIX = 'QUICKSTART_'

# 根目录（.env / data / logs 均以此为基准）
try:
    root_dir = find_project_root()
except FileNotFoundError:
    root_dir = get_root_dir(__file__, 2)


# 项目全局配置
class Settings(AugmentBaseSettings):
    """项目全局配置，字段通过 QUICKSTART_ 前缀的环境变量或 .env 覆盖

    Example:
        .env 中写 ``QUICKSTART_LOGS_DIR="./data/logs"`` 即可覆盖日志目录
    """
    # 数据库配置（默认 SQLite 落盘于项目 data/ 目录，可经 QUICKSTART_DATABASE__* 覆盖）
    database: DatabaseSettings = Field(
        default_factory=lambda: DatabaseSettings(
            engine='sqlite',
            name=str(root_dir / 'data' / 'quickstart.db'),
        )
    )

    # 日志配置（对应 fastapi_augment.logger.setup_logger 参数）
    logs_dir: str | Path | None = root_dir / 'logs'  # 日志保存目录（null=不开启文件日志）
    logs_level: str | None = 'INFO'  # 日志级别（set_log_level）
    logs_filename: str = 'app.log'  # 日志文件名
    logs_rotation: str = 'hour'  # 轮转粒度: second/minute/hour/day/week/month/year
    logs_backup_count: int = 30  # 保留的历史日志文件数量
    logs_encoding: str = 'utf-8'  # 文件编码
    logs_enable_console: bool = True  # 是否在控制台输出日志

    @property
    def root_dir(self) -> Path:
        """根目录

        Returns:
            根目录路径
        """
        return root_dir


# 配置实例
settings = Settings.from_env(
    env_file=root_dir / '.env',
    env_prefix=ENV_PREFIX,
    env_nested_delimiter='__',
    env_parse_none_str='null'
)
