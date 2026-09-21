"""
@Author         : hangu
@CreateDate     : 2026/9/14
@Description    : 发现并加载 apps 包下通过 __all__ 导出的 FastAPI 应用实例
约定：
    每个业务子包（如 apps.platform）在其 __init__.py 中通过 __all__ 导出
    自己创建的 FastAPI 实例（如 platform_app）。只有出现在子包 __init__.py
    的 __all__ 里、且确实是 FastAPI 实例的对象才会被识别为"应用"，
    其它一律不算。
    主应用由配置自行定义（settings.project.main_app，如
    ``apps.platform:platform_app``），不参与自动发现；
    discover_fastapi_apps(exclude=主应用) 用于获取主应用之外的其它应用。
"""
from collections.abc import Iterator
from dataclasses import dataclass
from importlib import import_module
from logging import getLogger
from pathlib import Path
from pkgutil import walk_packages
from types import ModuleType

from fastapi import FastAPI

_logger = getLogger(__name__)


@dataclass(frozen=True)
class FastAPIAppSpec:
    """FastAPI 应用装载信息

    Attributes:
        module: 应用所在模块，如 ``apps.platform``
        name: 在子包 ``__all__`` 中的导出名，如 ``platform_app``
        app: FastAPI 应用实例
    """

    module: str
    name: str
    app: FastAPI

    @property
    def import_string(self) -> str:
        """返回 uvicorn 可用的 ``module:name`` 导入串"""
        return f'{self.module}:{self.name}'


def _iter_subpackages(root: str) -> Iterator[str]:
    """递归遍历 root 包下的所有子包（含深层）

    Args:
        root: 根包名

    Returns:
        子包的完全限定模块名迭代器
    """
    root_module = import_module(root)
    yield from (
        info.name
        for info in walk_packages(
            root_module.__path__,
            f'{root}.',
            onerror=lambda name: _logger.warning(f'子包 {name} 导入失败，已跳过'),
        )
        if info.ispkg
    )


def _iter_exported_apps(module: ModuleType) -> Iterator[tuple[str, FastAPI]]:
    """从模块的 __all__ 中筛出 FastAPI 实例

    Args:
        module: 子包模块（即其 __init__.py 对应的模块对象）

    Yields:
        (导出名, FastAPI 实例)；未定义 __all__ 或没有 FastAPI 实例时为空
    """
    exported: list[str] | None = getattr(module, '__all__', None)
    if not exported:
        return
    missing = object()
    for name in exported:
        obj = getattr(module, name, missing)
        if obj is missing:
            _logger.warning(f'{module.__name__}.__all__ 中的 {name!r} 不存在，已跳过')
            continue
        if isinstance(obj, FastAPI):
            yield name, obj


def discover_fastapi_apps(root: str | Path = 'apps', exclude: str | None = None) -> list[FastAPIAppSpec]:
    """发现 root 包下所有子包通过 __all__ 导出的 FastAPI 应用

    规则：
    1. 递归遍历 root 下的全部子包（如 ``apps.platform``）
    2. 只检查子包 ``__init__.py`` 中 ``__all__`` 列出的名字
    3. 名字对应的对象必须是 ``FastAPI`` 实例才计入，其它对象一律不算
    4. 结果按模块名排序，保证顺序稳定

    Args:
        root: 根包名，默认 ``apps``
        exclude: 需要排除的应用标识，支持模块名（``apps.platform``）、
            导出名（``platform_app``）或 ``module:name`` 导入串
            （``apps.platform:platform_app``）；通常传入主应用，用于获取
            主应用之外的其它应用

    Returns:
        按模块名排序的应用清单；未发现时返回空列表
    """
    root = str(root)
    specs: list[FastAPIAppSpec] = []
    for module_name in sorted(_iter_subpackages(root)):
        try:
            module = import_module(module_name)
        except (KeyboardInterrupt, SystemExit):
            raise
        except ModuleNotFoundError:
            _logger.exception(f'子包 {module_name!r} 不存在，已跳过')
            continue
        except ImportError:
            _logger.exception(f'子包 {module_name!r} 存在但导入失败，已跳过')
            continue
        for name, app in _iter_exported_apps(module):
            specs.append(FastAPIAppSpec(module=module_name, name=name, app=app))
    if exclude:
        specs = [spec for spec in specs if exclude not in (spec.module, spec.name, spec.import_string)]
    return specs


def _parse_import_string(import_string: str) -> tuple[str, str]:
    """解析 ``module:attr`` 导入串

    Args:
        import_string: uvicorn 导入串，如 ``apps.platform:platform_app``

    Returns:
        (模块名, 属性名)；无冒号时属性名默认为 ``app``

    Raises:
        ValueError: 导入串为空或格式错误
    """
    if not import_string.strip():
        raise ValueError('主应用导入串为空，请在 settings.project.main_app 中配置')
    if import_string.count(':') > 1:
        raise ValueError(f'主应用导入串格式错误（只能有一个 ":"）: {import_string!r}')
    module, _, attr = import_string.partition(':')
    module = module.strip()
    attr = attr.strip() or 'app'
    if not module:
        raise ValueError(f'主应用导入串格式错误（缺少模块名）: {import_string!r}')
    return module, attr


def validate_asgi_import(import_string: str) -> None:
    """校验 ASGI 应用导入字符串是否真实存在

    规则：
    1. 导入字符串为空（''）直接报错
    2. 格式须为 ``module:attr``（无冒号时默认取属性 ``app``）
    3. 模块必须可导入、属性必须真实存在
    4. 属性对象必须是 ``FastAPI`` 实例

    Args:
        import_string: uvicorn 导入串，如 ``apps.platform:platform_app``

    Raises:
        ValueError: 导入串为空或格式错误
        RuntimeError: 模块无法导入 / 属性不存在 / 不是 FastAPI 实例
    """
    module_name, attr = _parse_import_string(import_string)
    try:
        module = import_module(module_name)
    except Exception as exc:
        # 模块导入可能抛任意异常，统一包装为 RuntimeError 便于上层处理
        raise RuntimeError(f'主应用模块 {module_name!r} 无法导入: {exc}') from exc
    missing = object()
    app = getattr(module, attr, missing)
    if app is missing:
        raise RuntimeError(f'主应用模块 {module_name!r} 中不存在属性 {attr!r}，请检查模块定义')
    if not isinstance(app, FastAPI):
        # 消息含"类型"二字触发 TRY004 误报；RuntimeError 语义正确（应用校验错误）
        raise RuntimeError(f'{import_string} 不是 FastAPI 应用（实际类型: {type(app).__name__}）')  # noqa: TRY004
