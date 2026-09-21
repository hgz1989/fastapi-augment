"""
common.utils.paths 模块测试 — 项目根目录定位
"""
from pathlib import Path

import pytest

from fastapi_augment.common.utils import (
    find_project_root,
    get_root_dir
)


# ── find_project_root ──────────────────────────────────────────────

class TestFindProjectRoot:

    def test_finds_pyproject_marker(self, tmp_path: Path):
        root = tmp_path / 'myproj'
        root.mkdir(parents=True)
        (root / 'pyproject.toml').write_text('')
        (root / 'pkg' / 'sub').mkdir(parents=True)
        assert find_project_root(root / 'pkg' / 'sub') == root.resolve()

    def test_finds_git_dir(self, tmp_path: Path):
        root = tmp_path / 'repo'
        (root / '.git').mkdir(parents=True)
        assert find_project_root(root) == root.resolve()

    def test_from_file_anchor(self, tmp_path: Path):
        root = tmp_path / 'app'
        root.mkdir(parents=True)
        (root / 'requirements.txt').write_text('')
        code_file = root / 'src' / 'main.py'
        code_file.parent.mkdir(parents=True)
        code_file.write_text('')
        assert find_project_root(code_file) == root.resolve()

    def test_default_is_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / 'setup.py').write_text('')
        monkeypatch.chdir(tmp_path)
        assert find_project_root() == tmp_path.resolve()


# ── get_root_dir ────────────────────────────────────────────────────

class TestGetRootDir:

    def test_parent_index(self, tmp_path: Path):
        anchor = tmp_path / 'a' / 'b' / 'c.txt'
        anchor.parent.mkdir(parents=True)
        anchor.write_text('')
        assert get_root_dir(anchor, 2) == tmp_path.resolve()

    def test_negative_index_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match='parent_index'):
            get_root_dir(tmp_path, -1)