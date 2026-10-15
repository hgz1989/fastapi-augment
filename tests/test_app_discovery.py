"""
@Author         : hangu
@CreateDate     : 2026/9/21
@Description    : common.app_discovery 模块测试 — 应用发现与导入串校验
"""
from dataclasses import FrozenInstanceError
from importlib import import_module
from pathlib import Path
from sys import modules as _sys_modules
from textwrap import dedent
from types import ModuleType

import pytest

from fastapi_augment.common import (
    ASGIAppSpec,
    discover_asgi_apps,
    validate_asgi_import
)


def _write_init(package_dir: Path, dotted_name: str, code: str) -> None:
    """在临时包中创建子包及其 __init__.py"""
    target = package_dir
    for part in dotted_name.split('.'):
        target = target / part
        target.mkdir(parents=True, exist_ok=True)
    (target / '__init__.py').write_text(dedent(code), encoding='utf-8')


@pytest.fixture
def apps_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """创建 apps 包（platform / ai / utils / broken 四个子包）并加入 sys.path

    - platform：导出 ASGI 应用实例 platform_app
    - ai：导出 ASGI 应用实例 ai_app
    - utils：__all__ 导出非 ASGI 对象（不计入发现结果）
    - broken：导入即失败（应被跳过，不中断发现）
    """
    root = tmp_path / 'pkg'
    _write_init(root, 'apps', '')
    _write_init(root, 'apps.platform', '''
        from fastapi import FastAPI

        platform_app = FastAPI()
        __all__ = ['platform_app']
    ''')
    _write_init(root, 'apps.ai', '''
        from fastapi import FastAPI

        ai_app = FastAPI()
        __all__ = ['ai_app']
    ''')
    _write_init(root, 'apps.utils', '''
        NOT_AN_APP = 'string'
        __all__ = ['NOT_AN_APP']
    ''')
    _write_init(root, 'apps.broken', '''
        import not_existing_module_xyz  # noqa: F401
    ''')
    monkeypatch.syspath_prepend(str(root))
    return root


# ── validate_asgi_import ────────────────────────────────────────────

class TestValidateAsgiImport:

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match='导入串为空'):
            validate_asgi_import('')

    def test_whitespace_raises(self):
        with pytest.raises(ValueError, match='导入串为空'):
            validate_asgi_import('   ')

    def test_multiple_colons_raises(self):
        with pytest.raises(ValueError, match='只能有一个'):
            validate_asgi_import('a:b:c')

    def test_missing_module_raises(self):
        with pytest.raises(ValueError, match='缺少模块名'):
            validate_asgi_import(':app')

    def test_unimportable_module_raises(self):
        with pytest.raises(RuntimeError, match='无法导入'):
            validate_asgi_import('no_such_module_xyz:app')

    def test_missing_attr_raises(self):
        with pytest.raises(RuntimeError, match='不存在属性'):
            validate_asgi_import('fastapi:no_such_attr')

    def test_class_not_asgi_raises(self):
        # FastAPI 类（非实例）不可直接作为 ASGI 应用（uvicorn 不自动实例化）
        with pytest.raises(RuntimeError, match='不是可调用的 ASGI 应用'):
            validate_asgi_import('fastapi:FastAPI')

    def test_valid_import_string(self, apps_package: Path):
        validate_asgi_import('apps.platform:platform_app')

    def test_valid_import_string_without_colon(self, apps_package: Path):
        # 无冒号时默认取属性 app；apps.ai 无 app 属性，应报属性不存在
        with pytest.raises(RuntimeError, match='不存在属性'):
            validate_asgi_import('apps.ai')

    def test_plain_asgi_function_passes(self, monkeypatch: pytest.MonkeyPatch):
        # 任意 (scope, receive, send) 三参异步函数均可作为 ASGI 应用
        module = ModuleType('fake_asgi_mod')

        async def app(scope, receive, send):
            ...

        module.app = app  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_asgi_mod', module)
        validate_asgi_import('fake_asgi_mod:app')

    def test_scope_only_single_param_rejected(self, monkeypatch: pytest.MonkeyPatch):
        # 单参形态（app(scope) 返回处理函数）不被接受：uvicorn 自动判为 asgi3
        # 后以 (scope, receive, send) 调用会 TypeError，挂载消费方也不支持
        module = ModuleType('fake_asgi3_mod')

        async def app(scope):
            async def handler(receive, send):
                ...

            return handler

        module.app = app  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_asgi3_mod', module)
        with pytest.raises(RuntimeError, match='不是可调用的 ASGI 应用'):
            validate_asgi_import('fake_asgi3_mod:app')

    def test_asgi2_class_rejected(self, monkeypatch: pytest.MonkeyPatch):
        # ASGI2 类形态（实例化收 scope，实例以 (receive, send) 调用）不再支持：
        # 挂载消费方（Starlette mount）仅接受三参可调用，挂载后首个请求即 TypeError
        module = ModuleType('fake_asgi2_mod')

        class App:
            def __init__(self, scope):
                self.scope = scope

            async def __call__(self, receive, send):
                ...

        module.app = App  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_asgi2_mod', module)
        with pytest.raises(RuntimeError, match='不是可调用的 ASGI 应用'):
            validate_asgi_import('fake_asgi2_mod:app')

    def test_non_callable_raises(self, monkeypatch: pytest.MonkeyPatch):
        module = ModuleType('fake_bad_mod')
        module.app = 'not-a-callable'  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_bad_mod', module)
        with pytest.raises(RuntimeError, match='不是可调用的 ASGI 应用'):
            validate_asgi_import('fake_bad_mod:app')

    # ── factory 模式（对应 uvicorn --factory）─────────────────────────

    def test_factory_zero_arg_callable_passes(self, monkeypatch: pytest.MonkeyPatch):
        module = ModuleType('fake_factory_mod')

        def create_app():
            return object()

        module.create_app = create_app  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_factory_mod', module)
        validate_asgi_import('fake_factory_mod:create_app', factory=True)

    def test_factory_all_defaults_callable_passes(self, monkeypatch: pytest.MonkeyPatch):
        """带默认值的参数等同无参可调用"""
        module = ModuleType('fake_factory_default_mod')

        def create_app(debug: bool = False):
            return object()

        module.create_app = create_app  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_factory_default_mod', module)
        validate_asgi_import('fake_factory_default_mod:create_app', factory=True)

    def test_factory_required_args_raises(self, monkeypatch: pytest.MonkeyPatch):
        """工厂函数有必填参数时，uvicorn 以 attr() 调用会失败，应提前报错"""
        module = ModuleType('fake_factory_args_mod')

        def create_app(settings):  # pragma: no cover - 仅签名用于校验
            return object()

        module.create_app = create_app  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_factory_args_mod', module)
        with pytest.raises(RuntimeError, match='无参调用'):
            validate_asgi_import('fake_factory_args_mod:create_app', factory=True)

    def test_factory_non_callable_raises(self, monkeypatch: pytest.MonkeyPatch):
        module = ModuleType('fake_factory_bad_mod')
        module.create_app = 'not-a-callable'  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_factory_bad_mod', module)
        with pytest.raises(RuntimeError, match='必须是可调用对象'):
            validate_asgi_import('fake_factory_bad_mod:create_app', factory=True)

    def test_factory_asgi_app_instance_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """ASGI 应用实例需要 (scope, receive, send) 三参，factory 模式下不可无参调用"""
        module = ModuleType('fake_factory_app_mod')

        async def app(scope, receive, send):
            ...

        module.app = app  # type: ignore[attr-defined]
        monkeypatch.setitem(_sys_modules, 'fake_factory_app_mod', module)
        with pytest.raises(RuntimeError, match='无参调用'):
            validate_asgi_import('fake_factory_app_mod:app', factory=True)

    def test_factory_flag_does_not_affect_default_mode(self, apps_package: Path):
        """不带 factory 标志时行为不变：ASGI 应用直接通过"""
        validate_asgi_import('apps.platform:platform_app')


# ── ASGIAppSpec ─────────────────────────────────────────────────────

class TestASGIAppSpec:

    def test_import_string_property(self):
        spec = ASGIAppSpec(module='apps.ai', name='ai_app', app=object())
        assert spec.import_string == 'apps.ai:ai_app'

    def test_frozen_instance(self):
        spec = ASGIAppSpec(module='apps.ai', name='ai_app', app=object())
        with pytest.raises(FrozenInstanceError):
            spec.name = 'other'


# ── discover_asgi_apps ──────────────────────────────────────────────

class TestDiscoverAsgiApps:

    def test_discovers_exported_apps(self, apps_package: Path):
        specs = discover_asgi_apps('apps')
        assert [spec.module for spec in specs] == ['apps.ai', 'apps.platform']
        assert [spec.name for spec in specs] == ['ai_app', 'platform_app']
        assert specs[0].app is import_module('apps.ai').ai_app
        assert specs[1].app is import_module('apps.platform').platform_app

    def test_excludes_by_module(self, apps_package: Path):
        specs = discover_asgi_apps('apps', exclude='apps.platform')
        assert [spec.module for spec in specs] == ['apps.ai']

    def test_excludes_by_name(self, apps_package: Path):
        specs = discover_asgi_apps('apps', exclude='ai_app')
        assert [spec.module for spec in specs] == ['apps.platform']

    def test_excludes_by_import_string(self, apps_package: Path):
        specs = discover_asgi_apps('apps', exclude='apps.platform:platform_app')
        assert [spec.module for spec in specs] == ['apps.ai']

    def test_ignores_non_app_exports(self, apps_package: Path):
        # apps.utils 的 __all__ 导出非 ASGI 对象，不应计入
        modules = {spec.module for spec in discover_asgi_apps('apps')}
        assert 'apps.utils' not in modules

    def test_skips_broken_subpackage(self, apps_package: Path):
        # apps.broken 导入失败应被跳过，不中断整个发现过程
        specs = discover_asgi_apps('apps')
        assert 'apps.broken' not in {spec.module for spec in specs}

    def test_accepts_path_root(self, apps_package: Path):
        specs = discover_asgi_apps(Path('apps'))
        assert len(specs) == 2

    def test_unknown_root_raises(self):
        with pytest.raises(ModuleNotFoundError):
            discover_asgi_apps('no_such_root')

    def test_discovers_non_fastapi_asgi(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # 非 FastAPI 的普通 ASGI 函数也应被发现（不限于 FastAPI 实例）
        root = tmp_path / 'pkg2'
        _write_init(root, 'apps2', '')
        _write_init(root, 'apps2.web', (
            '            async def web_app(scope, receive, send):\n'
            '                ...\n'
            '\n'
            '            __all__ = [\'web_app\']\n'
        ))
        monkeypatch.syspath_prepend(str(root))
        specs = discover_asgi_apps('apps2')
        assert [spec.module for spec in specs] == ['apps2.web']
        assert [spec.name for spec in specs] == ['web_app']
