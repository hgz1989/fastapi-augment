"""Release 版本决策与代码版本同步

模式：
    release: 按规则确定目标版本并同步代码版本
        （无 tag 用代码版本 / 代码高于 tag 用代码版本 / 否则以 tag 版本为准）
    rebuild: 直接使用指定版本重新打包，不修改代码版本

同步：release 模式下，最终版本确定后把 VERSION 与 factory.py 中 create_app 的默认版本一并改为最终版本。
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def parse_version(version: str) -> tuple[int, int, int]:
    """解析语义化版本号，支持 ``1.2.3`` / ``v1.2.3``"""
    match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', version.strip())
    if not match:
        raise ValueError(f'无法解析版本号: {version!r}')
    return tuple(int(part) for part in match.groups())


def current_code_version(root: Path) -> str:
    """读取 VERSION 文件中的代码版本"""
    return (root / 'VERSION').read_text(encoding='utf-8').strip()


def latest_tag_version(root: Path) -> str | None:
    """获取仓库中版本最高的 tag，无合法版本 tag 时返回 None"""
    result = subprocess.run(
        ['git', 'tag', '--list'],
        cwd=root,
        capture_output=True,
        text=True,
    )
    tags = []
    for line in result.stdout.splitlines():
        tag = line.strip()
        try:
            parse_version(tag)
        except ValueError:
            continue
        tags.append(tag)
    if not tags:
        return None
    return max(tags, key=parse_version)


def decide_version(code_version: str, tag_version: str | None) -> str:
    """按规则确定最终版本"""
    if tag_version is None:
        return code_version
    if parse_version(code_version) > parse_version(tag_version):
        return code_version
    return tag_version.lstrip('v')


def sync_code_version(root: Path, version: str) -> bool:
    """把 VERSION 与 factory.py 的 create_app 默认版本同步为 version，返回是否有改动"""
    changed = False
    version_file = root / 'VERSION'
    if version_file.read_text(encoding='utf-8').strip() != version:
        version_file.write_text(version + '\n', encoding='utf-8')
        changed = True
    factory = root / 'src/fastapi_augment/factory.py'
    text = factory.read_text(encoding='utf-8')
    new_text, count = re.subn(
        r"(version: str = )'[^']*'",
        rf"\g<1>'{version}'",
        text,
        count=1,
    )
    if count == 0:
        raise RuntimeError('factory.py 中未找到 version: str = ... 默认参数')
    if new_text != text:
        factory.write_text(new_text, encoding='utf-8')
        changed = True
    return changed


def write_output(output_file: str | None, **values: str) -> None:
    """写入 GitHub Actions 的 GITHUB_OUTPUT；本地运行时跳过"""
    if not output_file:
        return
    with open(output_file, 'a', encoding='utf-8') as f:
        for key, value in values.items():
            f.write(f'{key}={value}\n')


def main() -> int:
    ap = argparse.ArgumentParser(description='Release 版本决策与代码版本同步')
    ap.add_argument('--mode', choices=['release', 'rebuild'], default='release')
    ap.add_argument('--rebuild-tag', default=None, help='rebuild 模式的目标版本 tag，如 v1.2.3')
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = ap.parse_args()
    root = args.root

    if args.mode == 'rebuild':
        if not args.rebuild_tag:
            print('::error::rebuild 模式必须提供 rebuild-tag（如 v1.2.3）', file=sys.stderr)
            return 2
        if not re.fullmatch(r'v\d+\.\d+\.\d+', args.rebuild_tag):
            print(f'::error::rebuild-tag 格式错误，应为 vX.Y.Z: {args.rebuild_tag!r}', file=sys.stderr)
            return 2
        final_version = args.rebuild_tag.lstrip('v')
        changed = False
        print(f'mode=rebuild rebuild_tag={args.rebuild_tag} final_version={final_version}')
    else:
        code_version = current_code_version(root)
        tag_version = latest_tag_version(root)
        final_version = decide_version(code_version, tag_version)
        changed = sync_code_version(root, final_version)
        print(f'mode=release code_version={code_version} tag_version={tag_version or "(none)"} final_version={final_version}')

    print(f'changed={changed}')
    write_output(os.environ.get('GITHUB_OUTPUT'), final_version=final_version, changed=str(changed).lower())
    return 0


if __name__ == '__main__':
    sys.exit(main())
