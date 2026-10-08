"""
@Author         : hangu
@CreateDate     : 2026/10/8
@Description    : alembic env.py 测试 — 异步驱动判定（含 dmAsync）与
                  模型模块导入失败硬报错
"""

import runpy
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest


def _env_py_path() -> Path:
    """定位安装包内的 alembic env.py"""
    import fastapi_augment

    return Path(fastapi_augment.__file__).parent / 'db' / 'sqlalchemy' / 'alembic' / 'env.py'


def _run_env(monkeypatch: pytest.MonkeyPatch, models_env: str | None = None) -> dict:
    """以打桩的 alembic context（offline 模式）执行 env.py

    先预热 ``fastapi_augment.db.sqlalchemy`` 的真实导入链——其内部的
    ``from alembic import command`` 必须在打桩前完成，否则会从假 alembic
    上取不到 command 属性而误报 ImportError

    Returns:
        env.py 模块命名空间（可访问 _is_async_url / target_metadata 等）
    """
    import fastapi_augment.db.sqlalchemy  # noqa: F401

    if models_env is None:
        monkeypatch.delenv('FASTAPI_AUGMENT_MODELS', raising=False)
    else:
        monkeypatch.setenv('FASTAPI_AUGMENT_MODELS', models_env)

    fake_context = SimpleNamespace(
        config=SimpleNamespace(
            config_file_name=None,
            config_ini_section='alembic',
            get_main_option=mock.Mock(return_value=None),
            get_section=mock.Mock(return_value={}),
        ),
        is_offline_mode=mock.Mock(return_value=True),
        configure=mock.Mock(),
        begin_transaction=mock.Mock(return_value=nullcontext()),
        run_migrations=mock.Mock(),
    )
    fake_alembic = SimpleNamespace(context=fake_context)

    with mock.patch.dict(sys.modules, {'alembic': fake_alembic}):
        return runpy.run_path(str(_env_py_path()))


# ── 异步驱动判定 ──────────────────────────────────────────────────────────

class TestAsyncDriverDetection:

    def test_dm_async_driver_detected(self, monkeypatch):
        """dm+dmAsync 驱动的 URL 被识别为异步（原缺陷：漏配 dmAsync）"""
        ns = _run_env(monkeypatch)
        assert ns['_is_async_url']('dm+dmAsync://SYSDBA:pwd@localhost:5236/SYSDBA') is True

    @pytest.mark.parametrize(
        'url',
        [
            'postgresql+asyncpg://u:p@localhost/db',
            'mysql+aiomysql://u:p@localhost/db',
            'mysql+asyncmy://u:p@localhost/db',
            'sqlite+aiosqlite:///app.db',
            'mssql+aioodbc://u:p@localhost/db',
        ],
    )
    def test_common_async_drivers(self, monkeypatch, url):
        """常见异步驱动均识别为异步"""
        ns = _run_env(monkeypatch)
        assert ns['_is_async_url'](url) is True

    @pytest.mark.parametrize(
        'url',
        [
            'postgresql+psycopg2://u:p@localhost/db',
            'mysql+pymysql://u:p@localhost/db',
            'sqlite+pysqlite:///app.db',
            'dm+dmPython://SYSDBA:pwd@localhost:5236/SYSDBA',
        ],
    )
    def test_sync_drivers_not_async(self, monkeypatch, url):
        """同步驱动不误判为异步"""
        ns = _run_env(monkeypatch)
        assert ns['_is_async_url'](url) is False


# ── 模型导入失败硬报错 ─────────────────────────────────────────────────────

class TestModelImportFailures:

    def test_missing_module_raises(self, monkeypatch):
        """导入失败必须抛 ImportError（原缺陷：静默 warning 后 autogenerate 误删表）"""
        with pytest.raises(ImportError, match='nonexistent_module_xyz'):
            _run_env(monkeypatch, models_env='nonexistent_module_xyz')

    def test_partial_failure_lists_all_failed(self, monkeypatch):
        """多模块中部分失败时，仅失败的模块出现在报错信息里"""
        with pytest.raises(ImportError) as exc_info:
            _run_env(monkeypatch, models_env='json,another_missing_module')
        assert 'another_missing_module' in str(exc_info.value)
        assert 'json' not in str(exc_info.value)

    def test_importable_module_loads_cleanly(self, monkeypatch):
        """模块可正常导入时 env.py 正常加载"""
        ns = _run_env(monkeypatch, models_env='json')
        assert ns['target_metadata'] is not None

    def test_blank_entries_ignored(self, monkeypatch):
        """空字符串 / 空白项 / 逗号空隙不触发导入也不抛错"""
        ns = _run_env(monkeypatch, models_env=' , ,')
        assert ns['target_metadata'] is not None

    def test_offline_mode_runs_migrations(self, monkeypatch):
        """offline 模式下正常走 run_migrations 流程"""
        ns = _run_env(monkeypatch)
        assert ns['context'].run_migrations.called
