"""
lifespan 模块测试 — HookRegistry / fastapi_lifespan / clear_hooks
"""
import asyncio

import pytest
from fastapi import FastAPI

from fastapi_augment.lifespan import (
    HookRegistry,
    core_registry,
    fastapi_lifespan,
    clear_hooks
)


# ── HookRegistry 基础注册 ─────────────────────────────────────────────

class TestHookRegistryRegister:
    """测试钩子注册行为"""

    def test_register_startup_hook(self, registry: HookRegistry):
        async def my_hook(): ...

        registry.register_startup(my_hook)
        assert len(registry._startup_hooks) == 1
        assert registry._startup_hooks[0].func is my_hook

    def test_register_shutdown_hook(self, registry: HookRegistry):
        async def my_hook(): ...

        registry.register_shutdown(my_hook)
        assert len(registry._shutdown_hooks) == 1

    def test_reject_sync_function(self, registry: HookRegistry):
        def sync_hook(): ...

        with pytest.raises(TypeError, match='必须是async异步函数'):
            registry.register_startup(sync_hook)  # type: ignore

    def test_dedup_same_function(self, registry: HookRegistry):
        async def my_hook(): ...

        registry.register_startup(my_hook)
        registry.register_startup(my_hook)
        assert len(registry._startup_hooks) == 1

    def test_priority_ordering_startup_desc(self, registry: HookRegistry):
        """启动钩子按优先级降序排列（越大越先执行）"""
        async def low(): ...
        async def high(): ...
        async def mid(): ...

        registry.register_startup(low, priority=10)
        registry.register_startup(high, priority=90)
        registry.register_startup(mid, priority=50)

        names = [h.func.__name__ for h in registry._startup_hooks]
        assert names == ['high', 'mid', 'low']

    def test_priority_ordering_shutdown_asc(self, registry: HookRegistry):
        """关闭钩子按优先级升序排列"""
        async def low(): ...
        async def high(): ...

        registry.register_shutdown(high, priority=90)
        registry.register_shutdown(low, priority=10)

        names = [h.func.__name__ for h in registry._shutdown_hooks]
        assert names == ['low', 'high']

    def test_needs_app_detection_no_arg(self, registry: HookRegistry):
        async def no_arg_hook(): ...

        registry.register_startup(no_arg_hook)
        assert registry._startup_hooks[0].needs_app is False

    def test_needs_app_detection_with_app(self, registry: HookRegistry):
        async def app_hook(app: FastAPI): ...

        registry.register_startup(app_hook)
        assert registry._startup_hooks[0].needs_app is True

    def test_custom_timeout(self, registry: HookRegistry):
        async def my_hook(): ...

        registry.register_startup(my_hook, timeout=5.0)
        assert registry._startup_hooks[0].timeout == 5.0


# ── 装饰器语法 ────────────────────────────────────────────────────────

class TestHookRegistryDecorators:

    def test_on_startup_bare(self, registry: HookRegistry):
        @registry.on_startup
        async def my_hook(): ...

        assert len(registry._startup_hooks) == 1
        assert registry._startup_hooks[0].func is my_hook

    def test_on_startup_with_params(self, registry: HookRegistry):
        @registry.on_startup(priority=100, timeout=3)
        async def my_hook(): ...

        assert len(registry._startup_hooks) == 1
        assert registry._startup_hooks[0].priority == 100
        assert registry._startup_hooks[0].timeout == 3

    def test_on_shutdown_bare(self, registry: HookRegistry):
        @registry.on_shutdown
        async def my_hook(): ...

        assert len(registry._shutdown_hooks) == 1

    def test_on_shutdown_with_params(self, registry: HookRegistry):
        @registry.on_shutdown(priority=80, abort_on_exception=True)
        async def my_hook(): ...

        item = registry._shutdown_hooks[0]
        assert item.priority == 80
        assert item.abort_on_exception is True

    def test_decorator_returns_original_func(self, registry: HookRegistry):
        async def my_hook(): ...

        decorated = registry.on_startup(my_hook)
        assert decorated is my_hook


# ── 钩子执行 ──────────────────────────────────────────────────────────

class TestHookRegistryRunHooks:

    async def test_run_startup_executes_all(self, registry: HookRegistry, app: FastAPI):
        results = []

        async def hook_a():
            results.append('a')

        async def hook_b():
            results.append('b')

        registry.register_startup(hook_a)
        registry.register_startup(hook_b)
        await registry.run_startup(app)
        assert results == ['a', 'b']

    async def test_run_shutdown_executes_all(self, registry: HookRegistry, app: FastAPI):
        results = []

        async def hook_a():
            results.append('a')

        async def hook_b():
            results.append('b')

        registry.register_shutdown(hook_a)
        registry.register_shutdown(hook_b)
        await registry.run_shutdown(app)
        assert results == ['a', 'b']

    async def test_hook_receives_app(self, registry: HookRegistry, app: FastAPI):
        received = []

        async def hook(app: FastAPI):
            received.append(app)

        registry.register_startup(hook)
        await registry.run_startup(app)
        assert received == [app]

    async def test_abort_on_exception_startup(self, registry: HookRegistry, app: FastAPI):
        async def bad_hook():
            raise ValueError('boom')

        registry.register_startup(bad_hook, abort_on_exception=True)
        with pytest.raises(RuntimeError, match='终止'):
            await registry.run_startup(app)

    async def test_no_abort_on_exception_shutdown(self, registry: HookRegistry, app: FastAPI):
        """关闭钩子默认 abort_on_exception=False，异常不中断后续钩子"""
        results = []

        async def bad_hook():
            raise ValueError('boom')

        async def good_hook():
            results.append('ok')

        registry.register_shutdown(bad_hook, abort_on_exception=False)
        registry.register_shutdown(good_hook, abort_on_exception=False)
        await registry.run_shutdown(app)
        assert results == ['ok']

    async def test_timeout_raises_runtime_error(self, registry: HookRegistry, app: FastAPI):
        async def slow_hook():
            await asyncio.sleep(10)

        registry.register_startup(slow_hook, timeout=0.01, abort_on_exception=True)
        with pytest.raises(RuntimeError, match='超时'):
            await registry.run_startup(app)

    async def test_empty_hooks_noop(self, registry: HookRegistry, app: FastAPI):
        """空注册表执行不报错"""
        await registry.run_startup(app)
        await registry.run_shutdown(app)


# ── clear / list ──────────────────────────────────────────────────────

class TestHookRegistryUtilities:

    def test_clear(self, registry: HookRegistry):
        async def hook(): ...

        registry.register_startup(hook)
        registry.register_shutdown(hook)
        registry.clear()
        assert len(registry._startup_hooks) == 0
        assert len(registry._shutdown_hooks) == 0
        assert len(registry._startup_seen) == 0
        assert len(registry._shutdown_seen) == 0

    def test_list_startup_hooks(self, registry: HookRegistry):
        async def hook_a(): ...
        async def hook_b(): ...

        registry.register_startup(hook_a, priority=10)
        registry.register_startup(hook_b, priority=90)
        descriptions = registry.list_startup_hooks()
        assert len(descriptions) == 2
        assert 'hook_b' in descriptions[0]
        assert 'priority=90' in descriptions[0]

    def test_list_shutdown_hooks(self, registry: HookRegistry):
        async def hook_a(): ...

        registry.register_shutdown(hook_a)
        descriptions = registry.list_shutdown_hooks()
        assert len(descriptions) == 1
        assert 'hook_a' in descriptions[0]

    def test_format_hook_with_timeout(self, registry: HookRegistry):
        async def hook(): ...

        registry.register_startup(hook, timeout=10)
        desc = registry.list_startup_hooks()[0]
        assert '10s' in desc

    def test_format_hook_without_timeout(self, registry: HookRegistry):
        async def hook(): ...

        registry.register_startup(hook)
        desc = registry.list_startup_hooks()[0]
        assert 'None' in desc


# ── fastapi_lifespan ──────────────────────────────────────────────────

class TestFastapiLifespan:

    async def test_core_registry_always_first(self, app: FastAPI):
        """core_registry 的钩子始终最先执行"""
        order = []

        async def core_hook():
            order.append('core')

        async def user_hook():
            order.append('user')

        core_registry.register_startup(core_hook, priority=1)

        user_reg = HookRegistry()
        user_reg.register_startup(user_hook, priority=999)

        app.state.registries = [user_reg]
        async with fastapi_lifespan(app):
            pass
        assert order[0] == 'core'

    async def test_shutdown_reverse_order(self, app: FastAPI):
        """关闭钩子按注册表逆序执行"""
        order = []

        async def core_shutdown():
            order.append('core_shutdown')

        async def user_shutdown():
            order.append('user_shutdown')

        core_registry.register_shutdown(core_shutdown)

        user_reg = HookRegistry()
        user_reg.register_shutdown(user_shutdown)

        app.state.registries = [user_reg]
        async with fastapi_lifespan(app):
            pass
        assert order == ['user_shutdown', 'core_shutdown']

    async def test_no_registries_attribute(self, app: FastAPI):
        """app.state 没有 registries 属性时不报错"""
        if hasattr(app.state, 'registries'):
            delattr(app.state, 'registries')
        async with fastapi_lifespan(app):
            pass

    async def test_invalid_registries_type_filtered(self, app: FastAPI):
        """非 HookRegistry 实例被过滤，不报错"""
        app.state.registries = [HookRegistry(), 'not_a_registry', 42]
        async with fastapi_lifespan(app):
            pass


# ── clear_hooks 辅助函数 ─────────────────────────────────────────────

class TestClearHooks:

    def test_clear_hooks_default_core(self):
        async def hook(): ...

        core_registry.register_startup(hook)
        assert len(core_registry._startup_hooks) == 1
        clear_hooks()
        assert len(core_registry._startup_hooks) == 0

    def test_clear_hooks_specific_registry(self):
        reg = HookRegistry()

        async def hook(): ...

        reg.register_startup(hook)
        clear_hooks(reg)
        assert len(reg._startup_hooks) == 0
