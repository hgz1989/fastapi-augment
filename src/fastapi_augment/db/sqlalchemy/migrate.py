"""
@Author         : zarkhan
@CreateDate     : 2026/9/5
@Description    : 数据库迁移 CLI 与 Alembic 环境配置生成
"""
import argparse
import sys
from logging import getLogger
from os import environ
from pathlib import Path

from alembic import command
from alembic.config import Config

_logger = getLogger(__name__)

# ===================== alembic.ini 模板 =====================

_ALEMBIC_INI_TEMPLATE = """\
# A generic, single database configuration.

[alembic]
# path to migration scripts.
# this is typically a path given in POSIX (e.g. forward slashes)
# format, relative to the token %(here)s which refers to the location of this
# ini file
script_location = fastapi_augment.db.sqlalchemy:alembic
version_locations = %(here)s/migrations/versions

# template used to generate migration file names; The default value is %%(rev)s_%%(slug)s
# Uncomment the line below if you want the files to be prepended with date and time
# see https://alembic.sqlalchemy.org/en/latest/tutorial.html#editing-the-ini-file
# for all available tokens
# file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s
# Or organize into date-based subdirectories (requires recursive_version_locations = true)
# file_template = %%(year)d/%%(month).2d/%%(day).2d_%%(hour).2d%%(minute).2d_%%(second).2d_%%(rev)s_%%(slug)s

# sys.path path, will be prepended to sys.path if present.
# defaults to the current working directory.  for multiple paths, the path separator
# is defined by "path_separator" below.
prepend_sys_path = .


# timezone to use when rendering the date within the migration file
# as well as the filename.
# If specified, requires the tzdata library which can be installed by adding
# `alembic[tz]` to the pip requirements.
# string value is passed to ZoneInfo()
# leave blank for localtime
# timezone =

# max length of characters to apply to the "slug" field
# truncate_slug_length = 40

# set to 'true' to run the environment during
# the 'revision' command, regardless of autogenerate
# revision_environment = false

# set to 'true' to allow .pyc and .pyo files without
# a source .py file to be detected as revisions in the
# versions/ directory
# sourceless = false

# version location specification; This defaults
# to <script_location>/versions.  When using multiple version
# directories, initial revisions must be specified with --version-path.
# The path separator used here should be the separator specified by "path_separator"
# below.
# version_locations = %(here)s/bar:%(here)s/bat:%(here)s/alembic/versions

# path_separator; This indicates what character is used to split lists of file
# paths, including version_locations and prepend_sys_path within configparser
# files such as alembic.ini.
# The default rendered in new alembic.ini files is "os", which uses os.pathsep
# to provide os-dependent path splitting.
#
# Note that in order to support legacy alembic.ini files, this default does NOT
# take place if path_separator is not present in alembic.ini.  If this
# option is omitted entirely, fallback logic is as follows:
#
# 1. Parsing of the version_locations option falls back to using the legacy
#    "version_path_separator" key, which if absent then falls back to the legacy
#    behavior of splitting on spaces and/or commas.
# 2. Parsing of the prepend_sys_path option falls back to the legacy
#    behavior of splitting on spaces, commas, or colons.
#
# Valid values for path_separator are:
#
# path_separator = :
# path_separator = ;
# path_separator = space
# path_separator = newline
#
# Use os.pathsep. Default configuration used for new projects.
path_separator = os

# set to 'true' to search source files recursively
# in each "version_locations" directory
# new in Alembic version 1.10
# recursive_version_locations = false

# the output encoding used when revision files
# are written from script.py.mako
# output_encoding = utf-8

# database URL.  This is consumed by the user-maintained env.py script only.
# other means of configuring database URLs may be customized within the env.py
# file.
sqlalchemy.url = {db_url}

# set the version table name
version_table = migration_version

[post_write_hooks]
# post_write_hooks defines scripts or Python functions that are run
# on newly generated revision scripts.  See the documentation for further
# detail and examples

# format using "black" - use the console_scripts runner, against the "black" entrypoint
# hooks = black
# black.type = console_scripts
# black.entrypoint = black
# black.options = -l 79 REVISION_SCRIPT_FILENAME

# lint with attempts to fix using "ruff" - use the module runner, against the "ruff" module
# hooks = ruff
# ruff.type = module
# ruff.module = ruff
# ruff.options = check --fix REVISION_SCRIPT_FILENAME

# Alternatively, use the exec runner to execute a binary found on your PATH
# hooks = ruff
# ruff.type = exec
# ruff.executable = ruff
# ruff.options = check --fix REVISION_SCRIPT_FILENAME

# Logging configuration.  This is also consumed by the user-maintained
# env.py script only.
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""


# ===================== 内部工具 =====================

def _resolve_alembic_config(db_url: str | None = None, project_dir: Path | None = None) -> Config:
    """构造 Alembic Config 对象，读取项目根目录的 alembic.ini

    Args:
        db_url: 数据库连接URL（可选，不传则从 alembic.ini 读取）
        project_dir: 项目根目录（默认当前工作目录）

    Returns:
        Alembic 配置对象

    Raises:
        FileNotFoundError: 若根目录 alembic.ini 不存在，提示用户先执行 init
    """
    here = project_dir or Path.cwd()
    root_ini = here / 'alembic.ini'

    if not root_ini.exists():
        raise FileNotFoundError(
            f'未找到 {root_ini}，请先执行: fastapi-augment-migrate init --db-url "<数据库URL>"'
        )

    cfg = Config(str(root_ini))
    if db_url:
        cfg.set_main_option('sqlalchemy.url', db_url)
    return cfg


# ===================== init =====================

def init_project(db_url: str, project_dir: Path | None = None) -> None:
    """初始化项目迁移环境

    在项目根目录生成 alembic.ini 和 alembic/versions/ 目录
    若 alembic.ini 已存在则跳过，不覆盖

    Args:
        db_url: 数据库连接URL
        project_dir: 项目根目录
    """
    here = project_dir or Path.cwd()
    alembic_ini = here / 'alembic.ini'
    versions_dir = here / 'migrations' / 'versions'

    if alembic_ini.exists():
        _logger.info('%s 已存在，跳过（不会覆盖）', alembic_ini)
    else:
        ini_content = _ALEMBIC_INI_TEMPLATE.format(db_url=db_url)
        alembic_ini.write_text(ini_content)
        _logger.info('已创建 %s', alembic_ini)

    versions_dir.mkdir(parents=True, exist_ok=True)
    _logger.info('已确保 %s 存在', versions_dir)
    _logger.info('初始化完成，现在可以使用 generate 生成迁移了')


# ===================== upgrade / downgrade =====================

def upgrade(db_url: str | None = None, revision: str = 'head', project_dir: Path | None = None) -> None:
    """升级数据库

    Args:
        db_url: 数据库连接URL（可选，不传则从 alembic.ini 读取）
        revision: 目标修订版本
        project_dir: 项目根目录
    """
    cfg = _resolve_alembic_config(db_url, project_dir)
    command.upgrade(cfg, revision)


def downgrade(db_url: str | None = None, revision: str = '-1', project_dir: Path | None = None) -> None:
    """降级数据库

    Args:
        db_url: 数据库连接URL（可选，不传则从 alembic.ini 读取）
        revision: 目标修订版本
        project_dir: 项目根目录
    """
    cfg = _resolve_alembic_config(db_url, project_dir)
    command.downgrade(cfg, revision)


# ===================== generate =====================

def generate_migration(message: str, models: str, project_dir: Path | None = None) -> None:
    """生成迁移文件

    统一通过 Alembic Python API（``command.stamp`` / ``command.revision``）
    执行，避免子进程调用与运行环境不一致；stamp 与生成任一步失败都会抛错，
    不再静默跳过

    Args:
        message: 迁移描述信息
        models: 模型模块，多个用逗号分隔 (如 myapp.models)
        project_dir: 项目根目录

    Raises:
        FileNotFoundError: 根目录 alembic.ini 不存在
        RuntimeError: stamp 或生成迁移失败
    """
    here = project_dir or Path.cwd()
    alembic_ini = here / 'alembic.ini'
    versions_dir = here / 'migrations' / 'versions'

    # 检查 alembic.ini 是否存在（不自动创建，由 init 负责）
    if not alembic_ini.exists():
        raise FileNotFoundError(
            f'未找到 {alembic_ini}，请先执行: fastapi-augment-migrate init --db-url "<数据库URL>"'
        )

    # 确保 versions 目录存在
    versions_dir.mkdir(parents=True, exist_ok=True)

    # 设置环境变量，让库内的 env.py 能加载用户模型；执行完成后恢复原值
    old_models = environ.get('FASTAPI_AUGMENT_MODELS')
    environ['FASTAPI_AUGMENT_MODELS'] = models
    try:
        cfg = _resolve_alembic_config(None, here)

        # 先 stamp head，同步数据库版本标记，
        # 避免 "Target database is not up to date" 错误
        command.stamp(cfg, 'head')

        # 生成迁移脚本
        command.revision(cfg, message=message, autogenerate=True)
        _logger.info('迁移脚本已生成于 %s', versions_dir)
    except Exception as e:
        raise RuntimeError(f'生成迁移失败: {e}') from e
    finally:
        if old_models is None:
            environ.pop('FASTAPI_AUGMENT_MODELS', None)
        else:
            environ['FASTAPI_AUGMENT_MODELS'] = old_models


# ===================== CLI 入口 =====================

def cli_main() -> None:
    """数据库迁移工具 (fastapi-augment)"""
    parser = argparse.ArgumentParser(description='数据库迁移工具 (fastapi-augment)')
    subparsers = parser.add_subparsers(dest='command', required=True, help='子命令')

    # --- init ---
    init_parser = subparsers.add_parser('init', help='初始化项目迁移环境')
    init_parser.add_argument('--db-url', default='sqlite:///app.db', help='数据库连接 URL')
    init_parser.add_argument('--project-dir', type=Path, default=None, help='项目根目录（默认为当前工作目录）')

    # --- upgrade ---
    up_parser = subparsers.add_parser('upgrade', help='执行数据库迁移')
    up_parser.add_argument('--db-url', help='数据库连接 URL（不传则从 alembic.ini 读取）')
    up_parser.add_argument('--revision', default='head', help='目标版本 (默认: head)')
    up_parser.add_argument('--downgrade', action='store_true', help='降级而非升级')
    up_parser.add_argument('--project-dir', type=Path, default=None, help='项目根目录（默认为当前工作目录）')

    # --- generate ---
    gen_parser = subparsers.add_parser('generate', help='生成迁移脚本')
    gen_parser.add_argument('--message', required=True, help='迁移描述信息')
    gen_parser.add_argument('--models', required=True, help='模型模块，多个用逗号分隔 (如 myapp.models)')
    gen_parser.add_argument('--project-dir', type=Path, default=None, help='项目根目录（默认为当前工作目录）')

    args = parser.parse_args()

    try:
        if args.command == 'init':
            init_project(args.db_url, args.project_dir)
        elif args.command == 'upgrade':
            if args.downgrade:
                downgrade(args.db_url, args.revision, args.project_dir)
            else:
                upgrade(args.db_url, args.revision, args.project_dir)
        elif args.command == 'generate':
            generate_migration(args.message, args.models, args.project_dir)
        else:
            parser.print_help()
    except (FileNotFoundError, RuntimeError) as e:
        # CLI 报错仅输出错误信息，不打印堆栈（刻意不用 exception）
        _logger.error('%s', e)  # noqa: TRY400
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
