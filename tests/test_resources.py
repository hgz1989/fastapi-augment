"""
resources 模块测试 — 包资源读取（data URI）
"""
from pathlib import Path


from fastapi_augment.common.utils.resources import (
    ASSETS_DIR,
    file_data_uri,
    package_asset_data_uri,
)


class TestFileDataUri:

    def test_existing_file(self, tmp_path: Path):
        """存在的文件读取为正确的 data URI"""
        p = tmp_path / 'logo.png'
        p.write_bytes(b'\x89PNG\x0d\x0a\x1a\x0a')

        uri = file_data_uri(p)
        assert uri is not None
        assert uri.startswith('data:image/png;base64,')
        assert uri.endswith('iVBORw0KGgo=')  # PNG 文件签名 8 字节的 base64

    def test_missing_file_returns_none(self, tmp_path: Path):
        """不存在的文件返回 None"""
        assert file_data_uri(tmp_path / 'nope.png') is None

    def test_unknown_extension(self, tmp_path: Path):
        """未知扩展名回退 application/octet-stream"""
        p = tmp_path / 'logo.weird'
        p.write_bytes(b'abc')
        uri = file_data_uri(p)
        assert uri is not None
        assert uri.startswith('data:application/octet-stream;base64,')


class TestPackageAssetDataUri:

    def test_assets_dir_points_into_package(self):
        """ASSETS_DIR 指向包内 assets 目录"""
        assert ASSETS_DIR.name == 'assets'
        assert ASSETS_DIR.parent.name == 'fastapi_augment'

    def test_missing_asset_returns_none(self):
        """包内不存在的资源返回 None（默认无 logo 文件时行为不变）"""
        assert package_asset_data_uri('not-exist.png') is None

    def test_readme_asset_readable(self):
        """assets/README.md 随包分发，可读取为 data URI"""
        uri = package_asset_data_uri('README.md')
        assert uri is not None
        assert uri.startswith('data:')
