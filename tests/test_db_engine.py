"""
db.sqlalchemy.engine 模块测试 — NodeConfig / ClusterTopology / EngineManager
"""
import pytest

from fastapi_augment.db.sqlalchemy.engine import (
    NodeConfig,
    ClusterTopology,
    EngineManager
)


# ── NodeConfig ────────────────────────────────────────────────────────

class TestNodeConfig:

    def test_defaults(self):
        node = NodeConfig(url='sqlite+aiosqlite:///test.db')
        assert node.url == 'sqlite+aiosqlite:///test.db'
        assert node.pool_size == 5
        assert node.max_overflow == 10
        assert node.pool_timeout == 30.0
        assert node.pool_recycle == 3600
        assert node.pool_pre_ping is True
        assert node.echo is False
        assert node.connect_args == {}

    def test_custom_values(self):
        node = NodeConfig(
            url='postgresql+asyncpg://localhost/db',
            pool_size=20,
            max_overflow=30,
            echo=True,
        )
        assert node.pool_size == 20
        assert node.max_overflow == 30
        assert node.echo is True

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match='url must not be empty'):
            NodeConfig(url='')

    def test_negative_pool_size_raises(self):
        with pytest.raises(ValueError, match='pool_size'):
            NodeConfig(url='sqlite+aiosqlite:///test.db', pool_size=-1)

    def test_negative_max_overflow_raises(self):
        with pytest.raises(ValueError, match='max_overflow'):
            NodeConfig(url='sqlite+aiosqlite:///test.db', max_overflow=-1)

    def test_negative_pool_timeout_raises(self):
        with pytest.raises(ValueError, match='pool_timeout'):
            NodeConfig(url='sqlite+aiosqlite:///test.db', pool_timeout=-1)

    def test_pool_recycle_below_minus1_raises(self):
        with pytest.raises(ValueError, match='pool_recycle'):
            NodeConfig(url='sqlite+aiosqlite:///test.db', pool_recycle=-2)

    def test_pool_recycle_minus1_allowed(self):
        node = NodeConfig(url='sqlite+aiosqlite:///test.db', pool_recycle=-1)
        assert node.pool_recycle == -1

    def test_zero_pool_size_allowed(self):
        node = NodeConfig(url='sqlite+aiosqlite:///test.db', pool_size=0)
        assert node.pool_size == 0


# ── ClusterTopology ───────────────────────────────────────────────────

class TestClusterTopology:

    def test_single_node(self):
        t = ClusterTopology(primary=NodeConfig(url='sqlite+aiosqlite:///test.db'))
        assert t.is_single is True
        assert t.is_master_replica is False
        assert t.is_cluster is False

    def test_master_replica(self):
        t = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///primary.db'),
            replicas=[NodeConfig(url='sqlite+aiosqlite:///replica.db')],
        )
        assert t.is_single is False
        assert t.is_master_replica is True
        # is_cluster 在只有 replicas 没有 readonly 时也为 True
        assert t.is_cluster is True

    def test_full_cluster(self):
        t = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///primary.db'),
            replicas=[NodeConfig(url='sqlite+aiosqlite:///replica.db')],
            readonly=[NodeConfig(url='sqlite+aiosqlite:///readonly.db')],
        )
        assert t.is_single is False
        assert t.is_cluster is True

    def test_readonly_only_is_cluster(self):
        """只有 readonly 节点（无 replicas）也算 cluster"""
        t = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///primary.db'),
            readonly=[NodeConfig(url='sqlite+aiosqlite:///readonly.db')],
        )
        assert t.is_single is False
        assert t.is_cluster is True
        assert t.is_master_replica is False

    def test_get_all_read_sources(self):
        replica = NodeConfig(url='sqlite+aiosqlite:///replica.db')
        readonly = NodeConfig(url='sqlite+aiosqlite:///readonly.db')
        t = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///primary.db'),
            replicas=[replica],
            readonly=[readonly],
        )
        sources = t.get_all_read_sources()
        assert len(sources) == 2
        assert sources[0] is replica
        assert sources[1] is readonly

    def test_get_all_read_sources_empty(self):
        t = ClusterTopology(primary=NodeConfig(url='sqlite+aiosqlite:///test.db'))
        assert t.get_all_read_sources() == []


# ── EngineManager ─────────────────────────────────────────────────────

class TestEngineManager:

    async def test_start_single(self):
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///test.db')
        )
        manager = EngineManager(topology).start()
        try:
            assert manager.write_engine is not None
            assert manager.topology is topology
            # 单节点时 read engine 回退到 write engine
            assert manager.next_read_engine() is manager.write_engine
        finally:
            await manager.dispose()

    async def test_start_with_replicas(self):
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///primary.db'),
            replicas=[
                NodeConfig(url='sqlite+aiosqlite:///replica1.db'),
                NodeConfig(url='sqlite+aiosqlite:///replica2.db'),
            ],
        )
        manager = EngineManager(topology).start()
        try:
            engines = manager.engines
            assert 'primary' in engines
            assert 'read_0' in engines
            assert 'read_1' in engines
            assert len(engines) == 3
        finally:
            await manager.dispose()

    async def test_round_robin_read_engine(self):
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///primary.db'),
            replicas=[
                NodeConfig(url='sqlite+aiosqlite:///replica1.db'),
                NodeConfig(url='sqlite+aiosqlite:///replica2.db'),
            ],
        )
        manager = EngineManager(topology).start()
        try:
            e1 = manager.next_read_engine()
            e2 = manager.next_read_engine()
            # round-robin 应该返回不同的引擎
            assert e1 is not e2
            # 第三次回到第一个
            e3 = manager.next_read_engine()
            assert e3 is e1
        finally:
            await manager.dispose()

    async def test_get_engine_by_name(self):
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///test.db')
        )
        manager = EngineManager(topology).start()
        try:
            engine = manager.get_engine('primary')
            assert engine is manager.write_engine
        finally:
            await manager.dispose()

    async def test_get_engine_invalid_name_raises(self):
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///test.db')
        )
        manager = EngineManager(topology).start()
        try:
            with pytest.raises(KeyError):
                manager.get_engine('nonexistent')
        finally:
            await manager.dispose()

    async def test_dispose_clears_engines(self):
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///test.db')
        )
        manager = EngineManager(topology).start()
        assert len(manager.engines) > 0
        await manager.dispose()
        assert len(manager.engines) == 0

    async def test_start_returns_self(self):
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///test.db')
        )
        manager = EngineManager(topology)
        result = manager.start()
        assert result is manager
        await manager.dispose()

    async def test_start_idempotent(self):
        """重复 start() 幂等：不会重建引擎导致旧连接池泄漏"""
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///test.db')
        )
        manager = EngineManager(topology).start()
        first = manager.write_engine
        try:
            result = manager.start()
            assert result is manager
            assert manager.write_engine is first
            assert len(manager.engines) == 1
        finally:
            await manager.dispose()

    async def test_access_after_dispose_raises(self):
        """dispose 后再访问引擎抛出 RuntimeError 而非裸 KeyError"""
        topology = ClusterTopology(
            primary=NodeConfig(url='sqlite+aiosqlite:///test.db')
        )
        manager = EngineManager(topology).start()
        await manager.dispose()

        with pytest.raises(RuntimeError, match='dispose'):
            _ = manager.write_engine
        with pytest.raises(RuntimeError, match='dispose'):
            _ = manager.next_read_engine()
        with pytest.raises(RuntimeError, match='dispose'):
            _ = manager.get_engine('primary')
