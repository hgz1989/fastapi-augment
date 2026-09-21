"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 健康检查模块
                  - 可扩展的检查器模式（继承 BaseChecker）
                  - 内置 AppChecker（应用状态）和 DatabaseChecker（数据库连通性）
                  - create_health_router() 一键创建健康检查路由
"""
from .checker import (
    BaseChecker,
    CheckResult,
    HealthResponse,
    STATUS_HEALTHY,
    STATUS_DEGRADED,
    STATUS_UNHEALTHY
)
from .checkers import AppChecker, DatabaseChecker
from .router import create_health_router

__all__ = [
    # 基础
    'BaseChecker',
    'CheckResult',
    'HealthResponse',
    # 状态常量
    'STATUS_HEALTHY',
    'STATUS_DEGRADED',
    'STATUS_UNHEALTHY',
    # 内置检查器
    'AppChecker',
    'DatabaseChecker',
    # 路由工厂
    'create_health_router'
]
