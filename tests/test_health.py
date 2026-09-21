"""
health 模块测试 — 健康检查包
"""
import time

from fastapi import FastAPI
from starlette.testclient import TestClient

from fastapi_augment.health import (
    CheckResult,
    STATUS_HEALTHY,
    STATUS_DEGRADED,
    STATUS_UNHEALTHY,
    AppChecker,
    DatabaseChecker,
    create_health_router,
    BaseChecker
)
from fastapi_augment.health.checker import (
    _worst_status
)


# ── 模型与工具 ─────────────────────────────────────────────────────────


class TestCheckResult:

    def test_basic_fields(self):
        r = CheckResult(name='test', status=STATUS_HEALTHY, latency_ms=1.5)
        assert r.name == 'test'
        assert r.status == STATUS_HEALTHY
        assert r.latency_ms == 1.5
        assert r.details is None

    def test_with_details(self):
        r = CheckResult(name='db', status=STATUS_UNHEALTHY, details={'error': 'timeout'})
        assert r.details == {'error': 'timeout'}


class TestWorstStatus:

    def test_all_healthy(self):
        assert _worst_status(STATUS_HEALTHY, STATUS_HEALTHY) == STATUS_HEALTHY

    def test_one_degraded(self):
        assert _worst_status(STATUS_HEALTHY, STATUS_DEGRADED) == STATUS_DEGRADED

    def test_one_unhealthy(self):
        assert _worst_status(STATUS_HEALTHY, STATUS_UNHEALTHY) == STATUS_UNHEALTHY

    def test_degraded_and_unhealthy(self):
        assert _worst_status(STATUS_DEGRADED, STATUS_UNHEALTHY) == STATUS_UNHEALTHY


# ── AppChecker ────────────────────────────────────────────────────────


class TestAppChecker:

    async def test_name(self):
        c = AppChecker()
        assert c.name == 'app'

    async def test_check_without_start_time(self):
        app = FastAPI()
        result = await AppChecker().check(app)
        assert result.status == STATUS_HEALTHY
        assert result.details['uptime_seconds'] == 0.0
        assert result.details['version'] == app.version

    async def test_check_with_start_time(self):
        app = FastAPI()
        app.state.start_time = time.time() - 60
        result = await AppChecker().check(app)
        assert result.status == STATUS_HEALTHY
        assert result.details['uptime_seconds'] >= 59.0


# ── DatabaseChecker ───────────────────────────────────────────────────


class TestDatabaseChecker:

    async def test_name_default(self):
        c = DatabaseChecker()
        assert c.name == 'database'

    async def test_name_custom(self):
        c = DatabaseChecker(name='pg')
        assert c.name == 'pg'

    async def test_check_without_engine_manager(self):
        app = FastAPI()
        result = await DatabaseChecker().check(app)
        assert result.status == STATUS_UNHEALTHY
        assert 'engine_manager not found' in result.details['error']


# ── create_health_router ──────────────────────────────────────────────


def _make_app_with_health(**router_kwargs) -> FastAPI:
    """辅助：创建带健康检查路由的 FastAPI 实例"""
    app = FastAPI()
    app.include_router(create_health_router(**router_kwargs))
    return app


class TestHealthRouter:

    def test_health_endpoint_healthy(self):
        """无数据库时，仅 AppChecker 返回 healthy"""
        app = _make_app_with_health(include_db_check=False)
        client = TestClient(app)

        resp = client.get('/health')
        assert resp.status_code == 200

        data = resp.json()
        assert data['status'] == STATUS_HEALTHY
        assert len(data['checks']) == 1
        assert data['checks'][0]['name'] == 'app'

    def test_health_with_db_check_no_engine(self):
        """开启数据库检查但无 engine_manager 时，总体 unhealthy + 503"""
        app = _make_app_with_health(include_db_check=True)
        client = TestClient(app)

        resp = client.get('/health')
        assert resp.status_code == 503

        data = resp.json()
        assert data['status'] == STATUS_UNHEALTHY
        assert len(data['checks']) == 2

        db_check = next(c for c in data['checks'] if c['name'] == 'database')
        assert db_check['status'] == STATUS_UNHEALTHY

    def test_custom_path(self):
        """自定义路径"""
        app = _make_app_with_health(path='/ping', include_db_check=False)
        client = TestClient(app)

        resp = client.get('/ping')
        assert resp.status_code == 200
        assert resp.json()['status'] == STATUS_HEALTHY

    def test_extra_checkers(self):
        """自定义检查器"""

        class AlwaysDegradedChecker(BaseChecker):
            @property
            def name(self):
                return 'custom'

            async def check(self, app):
                return CheckResult(name=self.name, status=STATUS_DEGRADED, latency_ms=0.5)

        app = _make_app_with_health(
            include_db_check=False,
            extra_checkers=[AlwaysDegradedChecker()],
        )
        client = TestClient(app)

        resp = client.get('/health')
        assert resp.status_code == 200

        data = resp.json()
        assert data['status'] == STATUS_DEGRADED
        assert len(data['checks']) == 2
        names = [c['name'] for c in data['checks']]
        assert 'app' in names
        assert 'custom' in names

    def test_checker_exception_caught(self):
        """检查器抛异常时兜底为 unhealthy"""

        class BrokenChecker(BaseChecker):
            @property
            def name(self):
                return 'broken'

            async def check(self, app):
                raise RuntimeError('boom')

        app = _make_app_with_health(
            include_db_check=False,
            extra_checkers=[BrokenChecker()],
        )
        client = TestClient(app)

        resp = client.get('/health')
        assert resp.status_code == 503

        data = resp.json()
        broken = next(c for c in data['checks'] if c['name'] == 'broken')
        assert broken['status'] == STATUS_UNHEALTHY
        assert 'boom' in broken['details']['error']

    def test_custom_tags(self):
        """自定义 OpenAPI 标签"""
        router = create_health_router(tags=['Monitor'], include_db_check=False)
        app = FastAPI()
        app.include_router(router)

        # 通过 OpenAPI schema 验证 tag
        schema = app.openapi()
        health_path = schema['paths'].get('/health')
        assert health_path is not None
        assert 'Monitor' in health_path['get']['tags']
