"""
测试公共 fixtures
"""
import pytest
from fastapi import FastAPI

from fastapi_augment.lifespan import (
    core_registry,
    clear_hooks,
    HookRegistry
)


@pytest.fixture(autouse=True)
def _isolate_core_registry():
    """每个测试前后自动清空 core_registry，防止全局状态泄漏"""
    clear_hooks(core_registry)
    yield
    clear_hooks(core_registry)


@pytest.fixture()
def registry() -> HookRegistry:
    """返回一个空的独立 HookRegistry 实例"""
    return HookRegistry()


@pytest.fixture()
def app() -> FastAPI:
    """返回一个最小化的 FastAPI 实例"""
    return FastAPI()
