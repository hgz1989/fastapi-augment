"""
@Author         : hangu
@CreateDate     : 2026/9/20
@Description    : db.sqlalchemy.settings 模块测试 — NestedDatabaseSettings 数据库配置
                  字段式设计：engine / host / port 等基础字段 + 自动推导驱动与端口
"""

from typing import ClassVar

import pytest

from fastapi_augment.db.sqlalchemy import DatabaseSettings
from fastapi_augment.settings import AugmentBaseSettings


# ── 默认值推导 ──────────────────────────────────────────────────────────

class TestNestedDatabaseSettingsDefaults:

    def test_default_values(self):
        """全部字段带默认值，可无参实例化"""
        db = DatabaseSettings()
        assert db.engine == '<engine>'
        assert db.driver == ''
        assert db.port == 0
        assert db.pool_size == 10
        assert db.max_overflow == 20
        assert db.pool_pre_ping is True
        assert db.pool_recycle == 3600
        assert db.connect_timeout == 10
        assert db.command_timeout == 30

    def test_driver_auto_inferred(self):
        """driver 为空时按 engine 推导默认异步驱动"""
        db = DatabaseSettings(engine='postgresql')
        assert db.driver == 'asyncpg'

        db = DatabaseSettings(engine='mysql')
        assert db.driver == 'aiomysql'

        db = DatabaseSettings(engine='sqlite')
        assert db.driver == 'aiosqlite'

    def test_custom_driver_kept(self):
        """显式传入 driver 时不覆盖"""
        db = DatabaseSettings(engine='postgresql', driver='psycopg')
        assert db.driver == 'psycopg'

    def test_port_auto_inferred(self):
        """port 为 0 时按 engine 推导默认端口"""
        db = DatabaseSettings(engine='postgresql', host='localhost')
        assert db.port == 5432

        db = DatabaseSettings(engine='mysql', host='localhost')
        assert db.port == 3306

        db = DatabaseSettings(engine='dm', host='localhost')
        assert db.port == 5236

    def test_custom_port_kept(self):
        """显式传入 port 时保留"""
        db = DatabaseSettings(engine='postgresql', host='localhost', port=5433)
        assert db.port == 5433

    def test_engine_case_insensitive(self):
        """engine 大小写不敏感"""
        db = DatabaseSettings(engine='PostgreSQL', host='localhost')
        assert db.driver == 'asyncpg'
        assert db.port == 5432

    def test_unknown_engine_no_defaults(self):
        """未知 engine 不推导驱动和端口"""
        db = DatabaseSettings(engine='unknown', host='h')
        assert db.driver == ''
        assert db.port == 0


# ── URL 构建 ────────────────────────────────────────────────────────────

class TestNestedDatabaseSettingsUrl:

    def test_postgresql_url(self):
        db = DatabaseSettings(engine='postgresql', host='localhost', user='u', password='p', name='app')
        assert db.url == 'postgresql+asyncpg://u:p@localhost:5432/app'

    def test_mysql_url(self):
        db = DatabaseSettings(engine='mysql', host='localhost', user='u', password='p', name='app')
        assert db.url == 'mysql+aiomysql://u:p@localhost:3306/app'

    def test_sqlite_url_from_name(self):
        """sqlite 无 file_path 时回退到 name"""
        db = DatabaseSettings(engine='sqlite', name='app.db')
        assert db.url == 'sqlite+aiosqlite:///app.db'

    def test_sqlite_url_from_file_path(self):
        """sqlite 提供 file_path 时优先使用"""
        db = DatabaseSettings(engine='sqlite', name='app.db', file_path='data/app.db')
        assert db.url == 'sqlite+aiosqlite:///data/app.db'

    def test_dm_url(self):
        db = DatabaseSettings(engine='dm', host='h', user='u', password='p', name='app')
        assert db.url == 'dm+dmAsync://u:p@h:5236/app'

    def test_oracle_url(self):
        db = DatabaseSettings(engine='oracle', host='h', user='u', password='p', name='app')
        assert db.url == 'oracle+oracledb://u:p@h:1521/app'

    def test_mssql_url(self):
        db = DatabaseSettings(engine='mssql', host='h', user='u', password='p', name='app')
        assert db.url == 'mssql+aioodbc://u:p@h:1433/app'

    def test_sync_url_uses_sync_driver(self):
        """sync_url 使用同步驱动，供 Alembic 等工具使用"""
        db = DatabaseSettings(engine='postgresql', host='localhost', user='u', password='p', name='app')
        assert db.sync_url == 'postgresql+psycopg2://u:p@localhost:5432/app'

        db = DatabaseSettings(engine='sqlite', name='app.db')
        assert db.sync_url == 'sqlite+pysqlite:///app.db'

    def test_unknown_engine_empty_driver_falls_back(self):
        """未知 engine 无默认驱动时 drivername 回退纯 engine，不生成 engine+:// 无效 URL"""
        db = DatabaseSettings(engine='cockroachdb', host='h', user='u', password='p', name='app')
        assert db.url == 'cockroachdb://u:p@h:0/app'
        assert db.sync_url == 'cockroachdb://u:p@h:0/app'

    def test_url_cached(self):
        """url 为 cached_property，重复访问返回同一对象"""
        db = DatabaseSettings(engine='postgresql', host='localhost', user='u', password='p', name='app')
        assert db.url is db.url
        assert db.sync_url is db.sync_url

    def test_placeholder_engine_url_raises(self):
        """engine 未配置（占位符）时访问 url 直接报错，而非连接时才失败"""
        db = DatabaseSettings()
        with pytest.raises(ValueError, match='engine 未配置'):
            _ = db.url


# ── Query 参数构建 ──────────────────────────────────────────────────────

class TestNestedDatabaseSettingsQuery:

    def test_extra_query_parsed(self):
        db = DatabaseSettings(
            engine='postgresql', host='localhost', user='u', password='p', name='app',
            extra_query='sslmode=verify-full&options=-c%20search_path%3Dpublic',
        )
        # SQLAlchemy 会将 query 值中的 %20 解析为空格后重新编码为 +
        assert '?options=-c+search_path%3Dpublic&sslmode=verify-full' in db.url

    def test_application_name_added(self):
        db = DatabaseSettings(
            engine='postgresql', host='localhost', user='u', password='p', name='app',
            application_name='iam',
        )
        assert '?application_name=iam' in db.url

    def test_extra_query_and_application_name_merged(self):
        db = DatabaseSettings(
            engine='mysql', host='localhost', user='u', password='p', name='app',
            extra_query='charset=utf8mb4', application_name='iam',
        )
        assert '?application_name=iam&charset=utf8mb4' in db.url

    def test_ssl_mode_mapped_for_postgresql(self):
        """postgresql 的 SSL 参数名为 sslmode"""
        db = DatabaseSettings(
            engine='postgresql', host='localhost', user='u', password='p', name='app',
            ssl_mode='require',
        )
        assert '?sslmode=require' in db.url

    def test_ssl_mode_mapped_for_mysql(self):
        """mysql 的 SSL 参数名为 ssl_mode"""
        db = DatabaseSettings(
            engine='mysql', host='localhost', user='u', password='p', name='app',
            ssl_mode='require',
        )
        assert '?ssl_mode=require' in db.url

    def test_no_query_when_empty(self):
        """无额外参数时 URL 不带 query"""
        db = DatabaseSettings(engine='sqlite', name='app.db')
        assert '?' not in db.url


# ── 派生属性 ────────────────────────────────────────────────────────────

class TestNestedDatabaseSettingsProperties:

    def test_is_file_based(self):
        """sqlite 为文件型数据库"""
        assert DatabaseSettings(engine='sqlite', name='app.db').is_file_based is True
        assert DatabaseSettings(engine='postgresql', host='h').is_file_based is False

    def test_requires_refresh(self):
        """mysql / sqlite / dm 新增或更新后需要手动 refresh"""
        assert DatabaseSettings(engine='mysql', host='h').requires_refresh is True
        assert DatabaseSettings(engine='sqlite', name='app.db').requires_refresh is True
        assert DatabaseSettings(engine='dm', host='h').requires_refresh is True
        assert DatabaseSettings(engine='postgresql', host='h').requires_refresh is False


# ── 与 AugmentBaseSettings 集成 ─────────────────────────────────────────

class TestNestedDatabaseSettingsWithBaseSettings:

    def test_nested_env_loading(self, monkeypatch: pytest.MonkeyPatch):
        """作为嵌套字段，通过 env_nested_delimiter 从环境变量加载"""
        monkeypatch.setenv('DATABASE__ENGINE', 'postgresql')
        monkeypatch.setenv('DATABASE__HOST', '192.168.1.100')
        monkeypatch.setenv('DATABASE__PORT', '5433')
        monkeypatch.setenv('DATABASE__NAME', 'iam')
        monkeypatch.setenv('DATABASE__POOL_SIZE', '20')
        monkeypatch.setenv('DATABASE__ECHO', 'true')

        class AppSettings(AugmentBaseSettings):
            database: DatabaseSettings = DatabaseSettings(engine='sqlite', name='default.db')

        settings = AppSettings.from_env(env_nested_delimiter='__')
        assert settings.database.engine == 'postgresql'
        assert settings.database.host == '192.168.1.100'
        assert settings.database.port == 5433
        assert settings.database.name == 'iam'
        assert settings.database.pool_size == 20
        assert settings.database.echo is True

    def test_default_when_env_absent(self):
        """未设置环境变量时使用字段默认值"""
        class AppSettings(AugmentBaseSettings):
            database: DatabaseSettings = DatabaseSettings(engine='sqlite', name='app.db')

        settings = AppSettings.from_env(env_nested_delimiter='__')
        assert settings.database.engine == 'sqlite'
        assert settings.database.name == 'app.db'
        assert settings.database.url == 'sqlite+aiosqlite:///app.db'


# ── to_node_config 桥接 ──────────────────────────────────────────────

class TestToNodeConfig:
    """to_node_config：池参数 / 超时 / SSL 证书桥接到 NodeConfig"""

    PG: ClassVar[dict[str, str]] = {
        'engine': 'postgresql',
        'host': 'localhost',
        'user': 'u',
        'password': 'p',
        'name': 'app',
    }

    def test_pool_and_echo_mapped(self):
        """池参数与 echo 直接映射到 NodeConfig 同名字段"""
        from fastapi_augment.db.sqlalchemy.engine import NodeConfig

        db = DatabaseSettings(
            **self.PG,
            pool_enabled=False, pool_size=7, max_overflow=15,
            pool_timeout=12, pool_recycle=600, pool_pre_ping=False, echo=True,
        )
        node = db.to_node_config()
        assert isinstance(node, NodeConfig)
        assert node.url == db.url
        assert node.pool_enabled is False
        assert node.pool_size == 7
        assert node.max_overflow == 15
        assert node.pool_timeout == 12
        assert node.pool_recycle == 600
        assert node.pool_pre_ping is False
        assert node.echo is True

    def test_connect_and_command_timeout_asyncpg(self):
        """postgresql：connect_timeout→timeout，command_timeout→command_timeout"""
        db = DatabaseSettings(**self.PG, connect_timeout=5, command_timeout=9)
        node = db.to_node_config()
        assert node.connect_args == {'timeout': 5, 'command_timeout': 9}

    def test_connect_timeout_mysql(self):
        """mysql：connect_timeout→connect_timeout；command_timeout 无映射不写入"""
        db = DatabaseSettings(
            engine='mysql', host='h', user='u', password='p', name='n',
            connect_timeout=7, command_timeout=9,
        )
        node = db.to_node_config()
        assert node.connect_args == {'connect_timeout': 7}

    def test_zero_timeouts_omitted(self):
        """timeout 为 0 时不写入 connect_args"""
        db = DatabaseSettings(**self.PG, connect_timeout=0, command_timeout=0)
        assert db.to_node_config().connect_args == {}

    def test_unknown_engine_timeouts_omitted(self):
        """无映射的引擎（dm 等）不写超时，避免驱动报错"""
        db = DatabaseSettings(
            engine='dm', host='h', user='u', password='p', name='n',
            connect_timeout=5, command_timeout=9,
        )
        assert db.to_node_config().connect_args == {}

    def test_ssl_paths_mysql(self):
        """mysql：证书路径直接作为 aiomysql connect_args"""
        db = DatabaseSettings(
            engine='mysql', host='h', user='u', password='p', name='n',
            ssl_ca='/ca.pem', ssl_cert='/c.pem', ssl_key='/k.key',
        )
        node = db.to_node_config()
        assert node.connect_args['ssl_ca'] == '/ca.pem'
        assert node.connect_args['ssl_cert'] == '/c.pem'
        assert node.connect_args['ssl_key'] == '/k.key'

    def test_ssl_ca_postgresql_context(self, monkeypatch):
        """postgresql：ssl_ca 传入 create_default_context，结果作为 connect_args['ssl']"""
        import ssl as _ssl

        sentinel = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
        captured: dict = {}

        def fake_create_default_context(cafile=None):
            captured['cafile'] = cafile
            return sentinel

        monkeypatch.setattr(_ssl, 'create_default_context', fake_create_default_context)
        db = DatabaseSettings(**self.PG, ssl_ca='/ca.pem')
        node = db.to_node_config()
        assert node.connect_args['ssl'] is sentinel
        assert captured['cafile'] == '/ca.pem'

    def test_ssl_cert_postgresql_loads_chain(self, monkeypatch):
        """postgresql：ssl_cert / ssl_key 传入 load_cert_chain"""
        import ssl as _ssl

        class _FakeContext:
            loaded: tuple | None = None

            def load_cert_chain(self, certfile, keyfile=None, password=None):
                self.loaded = (certfile, keyfile)

        fake = _FakeContext()
        monkeypatch.setattr(_ssl, 'create_default_context', lambda cafile=None: fake)
        db = DatabaseSettings(**self.PG, ssl_cert='/c.pem', ssl_key='/k.key')
        node = db.to_node_config()
        assert node.connect_args['ssl'] is fake
        assert fake.loaded == ('/c.pem', '/k.key')

    def test_no_ssl_postgresql_no_context(self):
        """postgresql 未配置证书时不构造 SSLContext"""
        db = DatabaseSettings(**self.PG)
        assert 'ssl' not in db.to_node_config().connect_args

    def test_sqlite_node_config(self):
        """sqlite 也能桥接（connect_args 为空，池参数交给引擎侧忽略）"""
        db = DatabaseSettings(engine='sqlite', name='app.db')
        node = db.to_node_config()
        assert node.url == 'sqlite+aiosqlite:///app.db'
        assert node.connect_args == {}
