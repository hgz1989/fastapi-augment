"""打包源码为 zip 与 tar.gz（排除环境/缓存/构建产物目录）

用法：python release_package.py <version> [--root DIR] [--out DIR]
输出：<out>/fastapi_augment-<version>.zip 与 .tar.gz
"""
import argparse
import sys
import tarfile
import zipfile
from pathlib import Path

EXCLUDE_DIRS = {
    '.git',
    '.venv',
    '.idea',
    '__pycache__',
    '.pytest_cache',
    '.ruff_cache',
    'dist',
    'dist-release',
}
EXCLUDE_FILES = {'.DS_Store'}


def collect_files(root: Path) -> list[Path]:
    """收集源码文件（排除环境/缓存/构建产物），按路径排序保证确定性"""
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_dir():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in EXCLUDE_DIRS for part in rel_parts):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        files.append(path)
    return files


def package(root: Path, version: str, out_dir: Path) -> tuple[Path, Path]:
    """生成 zip 与 tar.gz，返回 (zip_path, tgz_path)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f'fastapi_augment-{version}'
    files = collect_files(root)

    zip_path = out_dir / f'{prefix}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, f'{prefix}/{path.relative_to(root).as_posix()}')

    tgz_path = out_dir / f'{prefix}.tar.gz'
    with tarfile.open(tgz_path, 'w:gz') as tf:
        for path in files:
            tf.add(path, f'{prefix}/{path.relative_to(root).as_posix()}')
    return zip_path, tgz_path


def main() -> int:
    ap = argparse.ArgumentParser(description='打包源码为 zip 与 tar.gz')
    ap.add_argument('version', help='目标版本号（不带 v 前缀）')
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument('--out', type=Path, default=None)
    args = ap.parse_args()
    out_dir = args.out or (args.root / 'dist-release')
    zip_path, tgz_path = package(args.root, args.version, out_dir)
    print(zip_path)
    print(tgz_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
