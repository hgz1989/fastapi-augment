"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 健康检查基础模型与检查器抽象基类
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import Field

from ..schemas import SchemaBase


# ── 结果模型 ──────────────────────────────────────────────────────────


class CheckResult(SchemaBase):
    """单项检查结果

    Attributes:
        name: 检查项名称
        status: 状态（healthy / degraded / unhealthy）
        latency_ms: 检查耗时（毫秒）
        details: 附加详情
    """
    name: str = Field(description='检查项名称')
    status: str = Field(description='状态：healthy / degraded / unhealthy')
    latency_ms: float = Field(default=0.0, description='检查耗时（毫秒）')
    details: dict[str, Any] = Field(default_factory=dict, description='附加详情')


class HealthResponse(SchemaBase):
    """健康检查响应体

    Attributes:
        status: 总体状态（取所有检查项中最差的状态）
        checks: 各检查项结果列表
    """
    status: str = Field(description='总体状态：healthy / degraded / unhealthy')
    checks: list[CheckResult] = Field(default_factory=list, description='各检查项结果')


# ── 状态常量 ──────────────────────────────────────────────────────────

STATUS_HEALTHY = 'healthy'
STATUS_DEGRADED = 'degraded'
STATUS_UNHEALTHY = 'unhealthy'

# 状态严重程度排序，用于聚合时取最差状态
_STATUS_SEVERITY = {STATUS_HEALTHY: 0, STATUS_DEGRADED: 1, STATUS_UNHEALTHY: 2}


def _worst_status(*statuses: str) -> str:
    """从多个状态中取最差的一个

    Args:
        *statuses: 待比较的状态字符串

    Returns:
        最差状态
    """
    return max(statuses, key=lambda s: _STATUS_SEVERITY.get(s, 99))


# ── 检查器基类 ────────────────────────────────────────────────────────


class BaseChecker(ABC):
    """健康检查器抽象基类

    所有检查器必须实现 ``name`` 属性和 ``check`` 异步方法::

        class RedisChecker(BaseChecker):
            @property
            def name(self) -> str:
                return 'redis'

            async def check(self, app: FastAPI) -> CheckResult:
                # 执行检查逻辑
                return CheckResult(name=self.name, status='healthy', latency_ms=1.2)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """检查项名称，用于标识和展示

        Returns:
            检查项名称
        """
        ...

    @abstractmethod
    async def check(self, app: Any) -> CheckResult:
        """执行健康检查

        Args:
            app: FastAPI 应用实例，可从中读取 app.state 等

        Returns:
            单项检查结果
        """
        ...
