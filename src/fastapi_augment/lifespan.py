"""
@Author         : hangu
@CreateDate     : 2026/9/3
@Description    : 应用生命周期钩子管理 (完整版)
                  - core_registry 始终在首位执行（基础/核心钩子）
                  - 支持多个自定义注册表，通过 app.state.registries 注入
                  - 每个注册表独立管理优先级、超时、异常策略
"""
import asyncio
from collections.abc import (
    Callable,
    AsyncGenerator,
    Sequence
)
from contextlib import asynccontextmanager
from dataclasses import dataclass
from inspect import iscoroutinefunction, signature
from logging import getLogger, Logger
from typing import (
    runtime_checkable,
    Protocol,
    overload
)

from fastapi import FastAPI

_logger = getLogger(__name__)

# -------------------------- 常量定义 --------------------------
DEFAULT_PRIORITY: int = 50
STARTUP_ABORT_ON_EXCEPTION: bool = True
SHUTDOWN_ABORT_ON_EXCEPTION: bool = False


# ---------- 类型定义 ----------
@runtime_checkable
class _NoArgHook(Protocol):
    """无参数钩子协议，用于类型检查"""

    async def __call__(self) -> None: ...


@runtime_checkable
class _AppArgHook(Protocol):
    """带 FastAPI 应用实例参数的钩子协议"""

    async def __call__(self, app: FastAPI) -> None: ...


HookFunc = _NoArgHook | _AppArgHook


@dataclass(frozen=True, slots=True)
class _HookItem:
    """钩子条目，存储单个钩子的元数据"""
    func: HookFunc
    priority: int
    abort_on_exception: bool
    needs_app: bool
    timeout: int | float | None = None


# ---------- 注册表 ----------
class HookRegistry:
    """生命周期钩子注册表

    每个实例独立管理自己的钩子列表，支持：
        - 注册启动/关闭钩子
        - 优先级控制（启动降序，关闭升序）
        - 超时控制
        - 异常时是否终止执行
        - 装饰器语法
        - 去重（基于函数 id）

    Attributes:
        _startup_hooks (list): 启动钩子列表
        _shutdown_hooks (list): 关闭钩子列表
        _startup_seen (set): 已注册的启动钩子函数 id 集合
        _shutdown_seen (set): 已注册的关闭钩子函数 id 集合
        _logger: 实例日志器
    """

    __slots__ = ('_logger', '_shutdown_hooks', '_shutdown_seen', '_startup_hooks', '_startup_seen')

    def __init__(self, logger: Logger | None = None):
        """初始化一个新的注册表实例，所有钩子列表为空"""
        self._startup_hooks: list[_HookItem] = []
        self._shutdown_hooks: list[_HookItem] = []
        self._startup_seen: set[int] = set()
        self._shutdown_seen: set[int] = set()
        self._logger = logger or _logger

    def register_startup(
            self,
            func: HookFunc,
            priority: int = DEFAULT_PRIORITY,
            abort_on_exception: bool = STARTUP_ABORT_ON_EXCEPTION,
            timeout: float | None = None,
    ) -> None:
        """注册启动钩子

        Args:
            func: 钩子函数
            priority: 优先级（越大越先执行）
            abort_on_exception: 异常时是否终止启动过程
            timeout: 超时秒数（None 表示不限制）
        """
        self._register(
            self._startup_hooks,
            self._startup_seen,
            func,
            priority,
            abort_on_exception,
            timeout,
            reverse_sort=True,
        )

    def register_shutdown(
            self,
            func: HookFunc,
            priority: int = DEFAULT_PRIORITY,
            abort_on_exception: bool = SHUTDOWN_ABORT_ON_EXCEPTION,
            timeout: float | None = None,
    ) -> None:
        """注册关闭钩子

        Args:
            func: 钩子函数
            priority: 优先级（越大越先执行）
            abort_on_exception: 异常时是否终止关闭过程
            timeout: 超时秒数（None 表示不限制）
        """
        self._register(
            self._shutdown_hooks,
            self._shutdown_seen,
            func,
            priority,
            abort_on_exception,
            timeout,
            reverse_sort=False,
        )

    @overload
    def on_startup(self, func: HookFunc, /) -> HookFunc: ...

    @overload
    def on_startup(
            self,
            *,
            priority: int = DEFAULT_PRIORITY,
            abort_on_exception: bool = STARTUP_ABORT_ON_EXCEPTION,
            timeout: float | None = None,
    ) -> Callable[[HookFunc], HookFunc]: ...

    def on_startup(
            self,
            func: HookFunc | None = None,
            *,
            priority: int = DEFAULT_PRIORITY,
            abort_on_exception: bool = STARTUP_ABORT_ON_EXCEPTION,
            timeout: float | None = None,
    ) -> Callable[[HookFunc], HookFunc] | HookFunc:
        """启动钩子装饰器

        可带参数调用：@registry.on_startup(priority=100)
        或不带参数：@registry.on_startup

        Args:
            func: 被装饰的函数
            priority: 优先级（越大越先执行）
            abort_on_exception: 异常时是否终止
            timeout: 超时秒数

        Returns:
            装饰器或原函数（取决于调用方式）
        """

        def decorator(fn: HookFunc) -> HookFunc:
            self.register_startup(fn, priority, abort_on_exception, timeout)
            return fn

        return decorator(func) if func else decorator

    @overload
    def on_shutdown(self, func: HookFunc, /) -> HookFunc: ...

    @overload
    def on_shutdown(
            self,
            *,
            priority: int = DEFAULT_PRIORITY,
            abort_on_exception: bool = SHUTDOWN_ABORT_ON_EXCEPTION,
            timeout: float | None = None,
    ) -> Callable[[HookFunc], HookFunc]: ...

    def on_shutdown(
            self,
            func: HookFunc | None = None,
            *,
            priority: int = DEFAULT_PRIORITY,
            abort_on_exception: bool = SHUTDOWN_ABORT_ON_EXCEPTION,
            timeout: float | None = None,
    ) -> Callable[[HookFunc], HookFunc] | HookFunc:
        """关闭钩子装饰器

        可带参数调用：@registry.on_shutdown(priority=100)
        或不带参数：@registry.on_shutdown

        Args:
            func: 被装饰的函数
            priority: 优先级（越大越先执行）
            abort_on_exception: 异常时是否终止
            timeout: 超时秒数

        Returns:
            装饰器或原函数（取决于调用方式）
        """

        def decorator(fn: HookFunc) -> HookFunc:
            self.register_shutdown(fn, priority, abort_on_exception, timeout)
            return fn

        return decorator(func) if func else decorator

    async def run_startup(self, app: FastAPI) -> None:
        """执行所有启动钩子

        Args:
            app: FastAPI 应用实例
        """
        if self._startup_hooks:
            self._logger.info(f'正在执行 {len(self._startup_hooks)} 个启动钩子 (注册表 {id(self)})...')
            await self._run_hooks(self._startup_hooks, app)
            self._logger.info('启动钩子执行完成')

    async def run_shutdown(self, app: FastAPI) -> None:
        """执行所有关闭钩子

        Args:
            app: FastAPI 应用实例
        """
        if self._shutdown_hooks:
            self._logger.info(f'正在执行 {len(self._shutdown_hooks)} 个关闭钩子 (注册表 {id(self)})...')
            await self._run_hooks(self._shutdown_hooks, app)
            self._logger.info('关闭钩子执行完成')

    def clear(self) -> None:
        """清空当前注册表中的所有钩子（包括启动和关闭）

        此方法会清空所有钩子列表和去重集合，用于测试环境隔离
        """
        self._startup_hooks.clear()
        self._shutdown_hooks.clear()
        self._startup_seen.clear()
        self._shutdown_seen.clear()

    def list_startup_hooks(self) -> list[str]:
        """返回按执行顺序排列的启动钩子描述列表

        Returns:
            钩子描述字符串列表，顺序即为执行顺序
        """
        return [self._format_hook(item) for item in self._startup_hooks]

    def list_shutdown_hooks(self) -> list[str]:
        """返回按执行顺序排列的关闭钩子描述列表

        Returns:
            钩子描述字符串列表，顺序即为执行顺序
        """
        return [self._format_hook(item) for item in self._shutdown_hooks]

    def _register(
            self,
            hooks: list[_HookItem],
            seen: set[int],
            func: HookFunc,
            priority: int,
            abort_on_exception: bool,
            timeout: float | None,
            reverse_sort: bool,
    ) -> None:
        """通用注册方法，供启动/关闭钩子复用

        Args:
            hooks: 目标钩子列表（启动或关闭）
            seen: 已注册函数 id 集合（用于去重）
            func: 待注册的钩子函数
            priority: 执行优先级
            abort_on_exception: 异常时是否终止执行
            timeout: 超时秒数
            reverse_sort: 排序方向（True 降序，False 升序）
        """
        func_id = id(func)
        if func_id in seen:
            self._logger.debug(f'钩子 {func.__name__} 已注册，跳过重复注册')
            return
        seen.add(func_id)

        # 校验必须是异步函数
        if not iscoroutinefunction(func):
            raise TypeError(f'生命周期钩子 `{func.__name__}` 必须是async异步函数')

        try:
            sig = signature(func)
            needs_app = len(sig.parameters) > 0
        except ValueError:
            # 无法解析签名，保守认为需要app参数，避免静默错误
            needs_app = True

        item = _HookItem(func, priority, abort_on_exception, needs_app, timeout)
        hooks.append(item)
        hooks.sort(key=lambda x: x.priority, reverse=reverse_sort)

    async def _run_hooks(self, hooks: list[_HookItem], app: FastAPI) -> None:
        """按序执行给定的钩子列表

        Args:
            hooks: 钩子条目列表
            app: FastAPI 应用实例

        Raises:
            RuntimeError: 当钩子超时或异常且 abort_on_exception=True 时抛出
        """
        for item in hooks:
            name = item.func.__name__
            timeout: int | float | None = item.timeout
            try:
                coro = item.func(app) if item.needs_app else item.func()
                if timeout is not None:
                    await asyncio.wait_for(coro, timeout=timeout)
                else:
                    await coro
            except TimeoutError:
                # TimeoutError 仅在 wait_for 分支触发，此处 timeout 必不为 None
                assert timeout is not None
                # 超时不记录堆栈，仅输出时长信息（刻意不用 exception）
                self._logger.error(  # noqa: TRY400
                    f'[生命周期钩子执行超时] {name}: 超过 {timeout}s',
                    exc_info=False
                )
                if item.abort_on_exception:
                    # 原始 TimeoutError 已由日志说明，无需保留异常链
                    raise RuntimeError(f'[启动/关闭终止：钩子 {name} 执行超时]') from None
            except Exception as e:
                self._logger.exception(f'[生命周期钩子执行失败] {name}')
                if item.abort_on_exception:
                    raise RuntimeError(f'[启动/关闭终止：钩子 {name} 异常]') from e

    @staticmethod
    def _format_hook(item: _HookItem) -> str:
        """将单个钩子条目格式化为可读的字符串

        Args:
            item: 钩子条目

        Returns:
            格式化后的字符串，如 'func_name(priority=50, abort=True, timeout=None)'
        """
        timeout_str = f'{item.timeout}s' if item.timeout is not None else 'None'
        return (
            f'{item.func.__name__}(priority={item.priority}, '
            f'abort={item.abort_on_exception}, timeout={timeout_str})'
        )


# ---------- 核心注册表（始终优先执行） ----------
core_registry = HookRegistry()


# ---------- FastAPI 生命周期 ----------
@asynccontextmanager
async def fastapi_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI 生命周期管理，强制 core_registry 在首位执行

    从 app.state.registries 读取用户自定义注册表列表（可选），
    并确保 core_registry 始终在列表最前面，以保证核心钩子优先执行

    启动时，按列表顺序执行每个注册表的 startup 钩子；
    关闭时，按逆序执行 shutdown 钩子，保证资源释放顺序符合依赖关系

    Example:
        app = FastAPI(lifespan=fastapi_lifespan)
        app.state.registries = [db_registry, cache_registry]
        # core_registry 会自动插入到列表首位

    Args:
        app: FastAPI 应用实例

    Yields:
        None

    Raises:
        TypeError: 当 app.state.registries 的类型不是 HookRegistry 或列表时
    """
    registries = getattr(app.state, 'registries', None)

    # 规范化输入
    if registries is None:
        registries = []
    elif isinstance(registries, HookRegistry):
        registries = [registries]
    elif isinstance(registries, Sequence):
        registries = list(registries)
    else:
        raise TypeError(
            f'app.state.registries 必须为 HookRegistry 或列表，实际为 {type(registries).__name__}'
        )

    # 过滤掉列表中非HookRegistry实例，防止异常
    registries = [r for r in registries if isinstance(r, HookRegistry)]

    # 去重（保留首次出现顺序）
    seen = set[int]()
    unique = []
    for reg in registries:
        rid = id(reg)
        if rid not in seen:
            seen.add(rid)
            unique.append(reg)
    registries = unique

    # ---- 强制 core_registry 在首位 ----
    core_id = id(core_registry)
    if core_id not in seen:
        registries.insert(0, core_registry)
    else:
        # 如果已在列表中，移除原有位置再插入首位（保持其他顺序不变）
        registries = [reg for reg in registries if id(reg) != core_id]
        registries.insert(0, core_registry)

    try:
        # 执行启动钩子（按列表顺序）
        for reg in registries:
            await reg.run_startup(app)
        yield  # 应用运行期间
    finally:
        # 无论启动阶段是否报错，都执行关闭钩子，防止资源泄漏
        for reg in reversed(registries):
            await reg.run_shutdown(app)


# ---------- 测试辅助 ----------
def clear_hooks(registry: HookRegistry | None = None) -> None:
    """清空注册表钩子，默认清空 core_registry（用于测试隔离）

    Args:
        registry: 需要清空的注册表实例；不传默认 core_registry
    """
    if registry is None:
        core_registry.clear()
    else:
        registry.clear()
