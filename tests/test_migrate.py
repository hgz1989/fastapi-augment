"""
db.sqlalchemy.migrate 模块测试 — 迁移 CLI 与工具函数
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from fastapi_augment.db.sqlalchemy.migrate import (
    init_project,
    _resolve_alembic_config,
    _fetch_current_async,
    _fetch_current_sync,
    cli_main
)


# ── init_project ──────────────────────────────────────────────────────

class TestInitProject:

    def test_creates_alembic_ini(self, tmp_path: Path):
        init_project('sqlite:///test.db', project_dir=tmp_path)
        ini = tmp_path / 'alembic.ini'
        assert ini.exists()
        content = ini.read_text()
        assert 'sqlite:///test.db' in content
        assert 'script_location' in content

    def test_creates_versions_dir(self, tmp_path: Path):
        init_project('sqlite:///test.db', project_dir=tmp_path)
        versions = tmp_path / 'migrations' / 'versions'
        assert versions.is_dir()

    def test_does_not_overwrite_existing_ini(self, tmp_path: Path):
        ini = tmp_path / 'alembic.ini'
        ini.write_text('# original content')
        init_project('sqlite:///other.db', project_dir=tmp_path)
        assert ini.read_text() == '# original content'

    def test_custom_db_url_in_ini(self, tmp_path: Path):
        init_project('postgresql+asyncpg://user:pass@host/db', project_dir=tmp_path)
        content = (tmp_path / 'alembic.ini').read_text()
        assert 'postgresql+asyncpg://user:pass@host/db' in content


# ── _resolve_alembic_config ───────────────────────────────────────────

class TestResolveAlembicConfig:

    def test_missing_ini_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match='请先执行'):
            _resolve_alembic_config(project_dir=tmp_path)

    def test_with_existing_ini(self, tmp_path: Path):
        init_project('sqlite:///test.db', project_dir=tmp_path)
        cfg = _resolve_alembic_config(project_dir=tmp_path)
        assert cfg.get_main_option('sqlalchemy.url') == 'sqlite:///test.db'

    def test_db_url_override(self, tmp_path: Path):
        init_project('sqlite:///test.db', project_dir=tmp_path)
        cfg = _resolve_alembic_config(db_url='sqlite:///override.db', project_dir=tmp_path)
        assert cfg.get_main_option('sqlalchemy.url') == 'sqlite:///override.db'


# ── cli_main ──────────────────────────────────────────────────────────

class TestCliMain:

    def test_init_command(self, tmp_path: Path):
        with patch('sys.argv', ['migrate', 'init', '--db-url', 'sqlite:///cli.db', '--project-dir', str(tmp_path)]):
            cli_main()
        assert (tmp_path / 'alembic.ini').exists()

    def test_upgrade_without_ini_exits(self, tmp_path: Path):
        with (
            patch('sys.argv', ['migrate', 'upgrade', '--project-dir', str(tmp_path)]),
            pytest.raises(SystemExit)
        ):
            cli_main()

    def test_generate_without_ini_exits(self, tmp_path: Path):
        with (
            patch('sys.argv', ['migrate', 'generate', '--message', 'test', '--models', 'models', '--project-dir', str(tmp_path)]),
            pytest.raises(SystemExit)
        ):
            cli_main()


# ── generate_migration ─────────────────────────────────────────────

class _FakeScript:
    """模拟 ScriptDirectory：head 为 None 表示项目尚无迁移文件"""

    def __init__(self, head: str | None = None):
        self._head = head

    def get_heads(self) -> list[str]:
        return [self._head] if self._head else []

    def get_head(self) -> str | None:
        return self._head


class TestGenerateMigration:

    def test_uses_command_api_and_restores_env(self, tmp_path: Path):
        """无迁移文件时跳过 stamp，走 revision 生成；环境变量执行后恢复"""
        import os

        from fastapi_augment.db.sqlalchemy.migrate import generate_migration

        init_project('sqlite:///test.db', project_dir=tmp_path)
        with patch('fastapi_augment.db.sqlalchemy.migrate.command.stamp') as mock_stamp, \
             patch('fastapi_augment.db.sqlalchemy.migrate.command.revision') as mock_revision, \
             patch.dict(os.environ, {'FASTAPI_AUGMENT_MODELS': 'old.models'}, clear=False):
            generate_migration('add table', 'app.models', project_dir=tmp_path)
            mock_stamp.assert_not_called()
            mock_revision.assert_called_once()
            assert os.environ['FASTAPI_AUGMENT_MODELS'] == 'old.models'

    def test_removes_env_when_absent(self, tmp_path: Path):
        """原环境无变量时，执行完彻底移除"""
        import os

        from fastapi_augment.db.sqlalchemy.migrate import generate_migration

        init_project('sqlite:///test.db', project_dir=tmp_path)
        os.environ.pop('FASTAPI_AUGMENT_MODELS', None)
        with patch('fastapi_augment.db.sqlalchemy.migrate.command.stamp'), \
             patch('fastapi_augment.db.sqlalchemy.migrate.command.revision'):
            generate_migration('add table', 'app.models', project_dir=tmp_path)
            assert 'FASTAPI_AUGMENT_MODELS' not in os.environ

    def test_stamp_failure_raises_runtime_error(self, tmp_path: Path):
        """已有迁移且数据库同步时，stamp 失败不再静默，统一抛 RuntimeError"""
        import fastapi_augment.db.sqlalchemy.migrate as migrate_mod

        from fastapi_augment.db.sqlalchemy.migrate import generate_migration

        init_project('sqlite:///test.db', project_dir=tmp_path)
        with patch.object(migrate_mod.ScriptDirectory, 'from_config', return_value=_FakeScript('abc')), \
             patch('fastapi_augment.db.sqlalchemy.migrate._db_is_synced', return_value=True), \
             patch('fastapi_augment.db.sqlalchemy.migrate.command.stamp', side_effect=RuntimeError('db down')), \
             pytest.raises(RuntimeError, match='生成迁移失败'):
            generate_migration('add table', 'app.models', project_dir=tmp_path)

    def test_generate_blocks_when_db_out_of_sync(self, tmp_path: Path):
        """数据库落后于 head 时中止生成，且不生成迁移脚本"""
        import fastapi_augment.db.sqlalchemy.migrate as migrate_mod

        from fastapi_augment.db.sqlalchemy.migrate import generate_migration

        init_project('sqlite:///test.db', project_dir=tmp_path)
        with patch.object(migrate_mod.ScriptDirectory, 'from_config', return_value=_FakeScript('abc')), \
             patch('fastapi_augment.db.sqlalchemy.migrate._db_is_synced', return_value=False), \
             patch('fastapi_augment.db.sqlalchemy.migrate.command.revision') as mock_revision, \
             pytest.raises(RuntimeError, match='upgrade'):
            generate_migration('add table', 'app.models', project_dir=tmp_path)
        mock_revision.assert_not_called()

    def test_stamp_used_when_heads_exist_and_synced(self, tmp_path: Path):
        """已有迁移且数据库同步时，stamp 正常执行"""
        import fastapi_augment.db.sqlalchemy.migrate as migrate_mod

        from fastapi_augment.db.sqlalchemy.migrate import generate_migration

        init_project('sqlite:///test.db', project_dir=tmp_path)
        with patch.object(migrate_mod.ScriptDirectory, 'from_config', return_value=_FakeScript('abc')), \
             patch('fastapi_augment.db.sqlalchemy.migrate._db_is_synced', return_value=True), \
             patch('fastapi_augment.db.sqlalchemy.migrate.command.stamp') as mock_stamp, \
             patch('fastapi_augment.db.sqlalchemy.migrate.command.revision'):
            generate_migration('add table', 'app.models', project_dir=tmp_path)
        mock_stamp.assert_called_once()


# ── _fetch_current_sync / _fetch_current_async ──────────────────────

def _prepare_version_table(db_path: Path) -> None:
    """用标准库 sqlite3 建表填值，避免测试依赖被测代码"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute('CREATE TABLE migration_version (version_num VARCHAR(32))')
    conn.execute("INSERT INTO migration_version (version_num) VALUES ('abc123')")
    conn.commit()
    conn.close()


class TestFetchCurrentVersion:
    """版本查询辅助函数：异步分支此前 text 未绑定被外层 except 静默吞掉"""

    def test_sync_reads_version(self, tmp_path: Path):
        db = tmp_path / 'sync.db'
        _prepare_version_table(db)
        assert _fetch_current_sync(f'sqlite:///{db}', 'migration_version') == 'abc123'

    async def test_async_reads_version(self, tmp_path: Path):
        db = tmp_path / 'async.db'
        _prepare_version_table(db)
        assert await _fetch_current_async(f'sqlite+aiosqlite:///{db}', 'migration_version') == 'abc123'
