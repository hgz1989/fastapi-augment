"""
@Author         : zarkhan
@CreateDate     : 2026/9/6
@Description    : 健康检查路由工厂
                  - 提供 create_health_router() 创建可配置的健康检查路由
                  - 自动注册 AppChecker，可选注册 DatabaseChecker 和自定义检查器
"""
from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Request, Response

from .checker import (
    BaseChecker,
    HealthResponse,
    CheckResult,
    STATUS_HEALTHY,
    _worst_status,
    STATUS_UNHEALTHY
)
from .checkers import AppChecker, DatabaseChecker


def create_health_router(
    *,
    path: str = '/health',
    tags: list[str] | None = None,
    include_db_check: bool = True,
    extra_checkers: Sequence[BaseChecker] | None = None,
) -> APIRouter:
    """创建健康检查路由

    默认包含 ``AppChecker``（应用状态），可选 ``DatabaseChecker``（数据库连通性），
    以及任意自定义检查器::

        from fastapi_augment.health import create_health_router

        # 最简用法：仅应用状态
        app.include_router(create_health_router(include_db_check=False))

        # 完整用法：应用 + 数据库 + 自定义检查器
        app.include_router(create_health_router(
            extra_checkers=[RedisChecker()],
        ))

    Args:

        path: 健康检查端点路径
        tags: OpenAPI 标签
        include_db_check: 是否包含数据库连通性检查（需要 app.state.engine_manager）
        extra_checkers: 额外的自定义检查器列表

    Returns:

        配置好的健康检查 APIRouter
    """
    router = APIRouter(tags=tags or ['Health'])

    # 组装检查器列表
    checkers: list[BaseChecker] = [AppChecker()]
    if include_db_check:
        checkers.append(DatabaseChecker())
    if extra_checkers:
        checkers.extend(extra_checkers)

    @router.get(path, response_model=HealthResponse)
    async def health_check(request: Request, response: Response) -> HealthResponse:
        """执行所有健康检查并返回聚合结果

        任一检查器返回 unhealthy 时，HTTP 状态码为 503

        Returns:
            聚合后的健康检查响应
        """
        results = []
        for checker in checkers:
            try:
                result = await checker.check(request.app)
            except Exception as e:  # noqa: BLE001
                # 检查器自身异常，兜底为 unhealthy
                result = CheckResult(
                    name=checker.name,
                    status=STATUS_UNHEALTHY,
                    details={'error': str(e)},
                )
            results.append(result)

        # 总体状态取最差
        overall = _worst_status(*(r.status for r in results)) if results else STATUS_HEALTHY

        # 不健康时返回 503
        if overall == STATUS_UNHEALTHY:
            response.status_code = 503

        return HealthResponse(status=overall, checks=results)

    return router
