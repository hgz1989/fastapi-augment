"""
@Author         : hangu
@CreateDate     : 2026/9/9
@Description    : 项目路径工具函数
"""
import sys
from pathlib import Path

# 项目根目录特征文件/目录，命中任一即视为项目根
_PROJECT_MARKERS = (
    'pyproject.toml',
    'setup.py',
    'setup.cfg',
    'requirements.txt',
    '.git',
    '.svn',
    '.hg',
)


def find_project_root(reference_path: str | Path | None = None) -> Path:
    """从参考路径向上搜索特征文件，自动定位项目根目录

    从 ``reference_path`` 所在目录开始逐级向上，命中任一特征文件
    （pyproject.toml / setup.py / setup.cfg / requirements.txt / .git 等）
    即返回该目录；``reference_path`` 缺省时从当前工作目录开始。
    相比 ``get_root_dir`` 的 ``parent_index`` 魔法层级数，文件移动后
    依然能正确定位

    Args:
        reference_path: 锚点参考路径（文件或目录），缺省为当前工作目录

    Returns:
        项目根目录绝对路径

    Raises:
        FileNotFoundError: 向上回溯到文件系统根仍未命中特征文件
    """
    start = Path(reference_path).resolve() if reference_path is not None else Path.cwd()
    if start.is_file():
        start = start.parent

    for candidate in (start, *start.parents):
        if any((candidate / marker).exists() for marker in _PROJECT_MARKERS):
            return candidate

    raise FileNotFoundError(
        f'未能在 {start} 及其上级目录中找到项目特征文件 {list(_PROJECT_MARKERS)}'
    )


# 获取项目根目录路径
def get_root_dir(reference_path: str | Path, parent_index: int) -> Path:
    """
    动态获取项目根目录路径，兼容源码开发环境与 PyInstaller/Nuitka 打包二进制环境

    源码模式：以传入的参考路径为基准，向上回溯 parent_index 层目录得到项目根；
    打包 frozen 模式：自动返回可执行文件(.exe/二进制)所在目录，忽略 reference_path、parent_index

    新代码建议优先使用 ``find_project_root()``，由特征文件自动定位根目录，
    无需维护 ``parent_index`` 层级下标

    Args:
        reference_path: 锚点参考路径，业务调用一般直接传入 __file__
        parent_index: 源码环境向上回溯层级下标

    Returns:
        项目根目录绝对路径

    Notes:
        parent_index >= 0；根据当前文件物理位置调整下标
    """
    if parent_index < 0:
        raise ValueError("parent_index 不能是负数")

    path = (
        Path(sys.executable).parent
        if getattr(sys, 'frozen', False)
        else Path(reference_path).parents[parent_index]
    )

    return path.resolve()
