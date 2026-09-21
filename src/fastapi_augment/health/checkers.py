"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 内置健康检查器
                  - AppChecker：应用基本信息（状态、版本、运行时长）
                  - DatabaseChecker：数据库连通性（基于 EngineManager）
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from sqlalchemy import text

from .checker import (
    BaseChecker,
    CheckResult,
    STATUS_HEALTHY,
    STATUS_UNHEALTHY
)

if TYPE_CHECKING:
    from ..db.sqlalchemy import EngineManager

# round() 精度（小数位数），提取为常量避免魔法数字
_ROUND_PRECISION: int = 2


class AppChecker(BaseChecker):
    """应用基本健康检查

    返回应用运行状态、版本、运行时长
    通过 ``app.state.start_time`` 获取启动时间戳（由工厂或用户设置）
    """

    @property
    def name(self) -> str:
        """应用检查器名称

        Returns:
            检查器名称
        """
        return 'app'

    async def check(self, app: Any) -> CheckResult:
        """检查应用状态

        Args:
            app: FastAPI 应用实例

        Returns:
            包含版本、状态、运行时长的检查结果
        """
        start_time = getattr(app.state, 'start_time', None)
        uptime = time.time() - start_time if isinstance(start_time, (int, float)) else 0.0

        return CheckResult(
            name=self.name,
            status=STATUS_HEALTHY,
            latency_ms=0.0,
            details={
                'status': 'running',
                'version': app.version if isinstance(app, FastAPI) else '',
                'uptime_seconds': round(uptime, _ROUND_PRECISION),
            },
        )


class DatabaseChecker(BaseChecker):
    """数据库连通性健康检查

    通过 ``app.state.engine_manager`` 获取写引擎，执行 ``SELECT 1`` 验证连通性
    若未挂载 ``engine_manager``，则跳过检查并返回 ``unhealthy``
    """

    def __init__(self, name: str = 'database'):
        self._name = name

    @property
    def name(self) -> str:
        """数据库检查器名称

        Returns:
            检查器名称
        """
        return self._name

    async def check(self, app: Any) -> CheckResult:
        """检查数据库连通性

        Args:
            app: FastAPI 应用实例

        Returns:
            数据库连通性检查结果
        """
        engine_manager: EngineManager | None = getattr(app.state, 'engine_manager', None)
        if engine_manager is None:
            return CheckResult(
                name=self.name,
                status=STATUS_UNHEALTHY,
                details={'error': 'engine_manager not found on app.state'},
            )

        start = time.perf_counter()
        try:
            engine = engine_manager.write_engine
            async with engine.connect() as conn:
                await conn.execute(text('SELECT 1'))
            latency = (time.perf_counter() - start) * 1000

            return CheckResult(
                name=self.name,
                status=STATUS_HEALTHY,
                latency_ms=round(latency, _ROUND_PRECISION),
            )
        except Exception as e:  # noqa: BLE001
            # 健康检查必须捕获所有异常：任何失败均标记为 unhealthy，不应向外抛出
            latency = (time.perf_counter() - start) * 1000
            return CheckResult(
                name=self.name,
                status=STATUS_UNHEALTHY,
                latency_ms=round(latency, _ROUND_PRECISION),
                details={'error': str(e)},
            )
