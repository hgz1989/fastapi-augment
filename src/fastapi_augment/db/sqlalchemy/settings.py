"""
@Author         : hangu
@CreateDate     : 2026/9/12
@Description    : 数据库配置——独立的嵌套 BaseModel，支持多数据库、自动推导驱动/端口
"""
from __future__ import annotations

import ssl
from functools import cached_property
from typing import Any, ClassVar, Self
from urllib.parse import parse_qsl

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator
)
from sqlalchemy import URL

from .engine import NodeConfig


class DatabaseSettings(BaseModel):
    """数据库配置（嵌套配置对象）

    .. note::
        **嵌套配置对象**：继承 :class:`~pydantic.BaseModel`（而非 ``BaseSettings``），
        不作为独立配置从环境变量加载，而是作为
        :class:`~fastapi_augment.settings.AugmentBaseSettings` 的一个字段嵌套使用，
        通过 ``IAM_DATABASE__`` 前缀的环境变量覆盖子字段。

    Example:
        .. code-block:: python

            class Settings(AugmentBaseSettings):
                database: DatabaseSettings = DatabaseSettings(engine='sqlite', name='app.db')

        .env 中写 ``IAM_DATABASE__HOST=192.168.1.100`` 即可覆盖 host
        .env 中写 ``IAM_DATABASE__ENGINE=mysql`` 即自动切换驱动和端口

        接入 :class:`~fastapi_augment.db.sqlalchemy.engine.EngineManager` 时用
        ``settings.database.to_node_config()`` 转为 NodeConfig（池参数 /
        连接超时 / SSL 证书自动按引擎桥接）
    """
    # ------------------------------
    # 类级别常量
    # ------------------------------
    # 使用文件路径而非 host/port 的数据库引擎
    _FILE_BASED: ClassVar[frozenset[str]] = frozenset({'sqlite'})
    # 需要手动 refresh 刷新默认值的数据库引擎
    _REQUIRES_REFRESH: ClassVar[frozenset[str]] = frozenset({'mysql', 'sqlite', 'dm'})
    # 各引擎的默认异步驱动
    _DEFAULT_DRIVERS: ClassVar[dict[str, str]] = {
        'postgresql': 'asyncpg',
        'mysql': 'aiomysql',
        'sqlite': 'aiosqlite',
        'dm': 'dmAsync',
        'oracle': 'oracledb',
        'mssql': 'aioodbc'
    }
    # 各引擎的同步驱动（供 Alembic 等工具使用）
    _SYNC_DRIVERS: ClassVar[dict[str, str]] = {
        'postgresql': 'psycopg2',
        'mysql': 'pymysql',
        'sqlite': 'pysqlite',
        'dm': 'dmPython',
        'oracle': 'oracledb',
        'mssql': 'pyodbc'
    }
    # 各引擎的默认端口
    _DEFAULT_PORTS: ClassVar[dict[str, int]] = {
        'postgresql': 5432,
        'mysql': 3306,
        'dm': 5236,
        'oracle': 1521,
        'mssql': 1433
    }
    # 各引擎在 URL query 中表示 SSL 模式的参数名
    _SSL_MODE_KEYS: ClassVar[dict[str, str]] = {
        'postgresql': 'sslmode',
        'mysql': 'ssl_mode',
        'dm': 'ssl_mode'
    }
    # connect_args 中"建立连接超时"的参数名（按引擎；未列出的引擎不写入）
    _CONNECT_TIMEOUT_KEYS: ClassVar[dict[str, str]] = {
        'postgresql': 'timeout',  # asyncpg
        'mysql': 'connect_timeout',  # aiomysql
    }
    # connect_args 中"单条命令执行超时"的参数名（按引擎；未列出的引擎不写入）
    _COMMAND_TIMEOUT_KEYS: ClassVar[dict[str, str]] = {
        'postgresql': 'command_timeout',  # asyncpg
    }

    model_config = ConfigDict(extra='ignore')

    # ------------------------------
    # 公共配置
    # ------------------------------
    engine: str = Field(
        default='<engine>',
        description='数据库引擎类型，决定驱动与默认端口',
        examples=['postgresql', 'mysql', 'sqlite', 'dm'],
    )
    host: str = Field(
        default='<host>',
        description='数据库主机地址；SQLite 无需填写',
        examples=['localhost', '192.168.1.100'],
    )
    port: int = Field(
        default=0,
        description='数据库端口；0 表示按 engine 自动推导',
        examples=[5432, 3306],
    )
    user: str = Field(
        default='<user>',
        description='数据库用户名；SQLite 无需填写',
        examples=['app_user'],
    )
    password: str = Field(
        default='<password>',
        description='数据库密码；SQLite 无需填写',
        examples=['secret'],
    )
    name: str = Field(
        default='<name>',
        description='数据库名称；SQLite 时为数据库文件名',
        examples=['app_db', 'app.db'],
    )
    file_path: str = Field(
        default='',
        description='SQLite 专用文件路径；为空时回退到 name',
        examples=['data/app.db'],
    )
    application_name: str = Field(
        default='',
        description='连接标识，便于 DBA 在 pg_stat_activity 等视图中定位来源',
        examples=['my-service'],
    )

    # 连接池
    pool_enabled: bool = Field(
        default=True,
        description='是否启用 SQLAlchemy 连接池',
        examples=[True],
    )
    pool_size: int = Field(
        default=10,
        description='连接池常驻连接数',
        examples=[10, 20],
    )
    max_overflow: int = Field(
        default=20,
        description='连接池最大溢出连接数（超过常驻后的临时连接上限）',
        examples=[20, 50],
    )
    pool_pre_ping: bool = Field(
        default=True,
        description='每次取连接前是否探测存活，避免获取失效连接',
        examples=[True],
    )
    pool_recycle: int = Field(
        default=3600,
        description='连接回收周期（秒），防止数据库端超时断连',
        examples=[3600, 1800],
    )
    pool_timeout: int = Field(
        default=30,
        description='连接池取连接的等待超时（秒）',
        examples=[30, 60],
    )

    # 超时
    connect_timeout: int = Field(
        default=10,
        description='建立 TCP 连接的等待超时（秒）',
        examples=[10, 30],
    )
    command_timeout: int = Field(
        default=30,
        description='单条 SQL 命令的执行超时（秒）',
        examples=[30, 60],
    )

    # ------------------------------
    # SSL（按需启用）
    # ------------------------------
    ssl_mode: str = Field(
        default='',
        description='SSL 模式：disable / require / verify-ca / verify-full；空表示不启用',
        examples=['disable', 'require', 'verify-ca', 'verify-full'],
    )
    ssl_ca: str = Field(
        default='',
        description='CA 证书文件路径（verify-ca / verify-full 时需要）',
        examples=['/etc/ssl/certs/ca.pem'],
    )
    ssl_cert: str = Field(
        default='',
        description='客户端证书文件路径',
        examples=['/etc/ssl/certs/client.pem'],
    )
    ssl_key: str = Field(
        default='',
        description='客户端私钥文件路径',
        examples=['/etc/ssl/private/client.key'],
    )

    # ------------------------------
    # SQLAlchemy 专属配置
    # ------------------------------
    driver: str = Field(
        default='',
        description='数据库驱动名；空表示按 engine 自动推导',
        examples=['asyncpg', 'aiomysql', 'aiosqlite'],
    )
    echo: bool = Field(
        default=False,
        description='是否输出 SQL 日志（调试用）',
        examples=[False, True],
    )
    extra_query: str = Field(
        default='',
        description='附加到连接 URL 的 query 参数，格式 a=1&b=2',
        examples=['charset=utf8&time_zone=%2B08:00'],
    )

    # ------------------------------
    # 校验与默认值推导
    # ------------------------------
    @cached_property
    def _engine_key(self) -> str:
        """engine 小写化后的键，多处属性复用以避免重复 lower()"""
        return self.engine.lower()

    @model_validator(mode='after')
    def _fill_defaults(self) -> Self:
        """根据 engine 推导 driver 和 port 的默认值

        Returns:
            填充默认值后的实例自身
        """
        engine = self._engine_key

        if not self.driver:
            self.driver = self._DEFAULT_DRIVERS.get(engine, '')

        if not self.port and engine not in self._FILE_BASED:
            self.port = self._DEFAULT_PORTS.get(engine, 0)

        return self

    # ------------------------------
    # 派生属性
    # ------------------------------
    @property
    def is_file_based(self) -> bool:
        """是否为文件型数据库（如 SQLite）

        Returns:
            是否为文件型数据库
        """
        return self._engine_key in self._FILE_BASED

    @property
    def requires_refresh(self) -> bool:
        """判断当前数据库引擎在新增/更新后是否需要手动 refresh 刷新默认值

        Returns:
            是否需要手动 refresh 刷新默认值
        """
        return self._engine_key in self._REQUIRES_REFRESH

    # ------------------------------
    # URL 构建
    # ------------------------------
    def _build_query(self) -> dict[str, str] | None:
        """构造 URL 中的 query 参数

        Returns:
            query 参数字典，无额外参数时返回 None
        """
        query: dict[str, str] = dict(parse_qsl(self.extra_query))

        if self.application_name:
            query.setdefault('application_name', self.application_name)

        if self.ssl_mode:
            key = self._SSL_MODE_KEYS.get(self._engine_key, 'ssl_mode')
            query.setdefault(key, self.ssl_mode)

        return query or None

    def _build_drivername(self, driver: str) -> str:
        """拼接 SQLAlchemy drivername；driver 为空时回退纯 ``engine``（交默认方言解析）

        Returns:
            拼接好的 drivername；driver 为空时仅返回 engine
        """
        return f'{self.engine}+{driver}' if driver else self.engine

    def _create_url(self, drivername: str) -> str:
        """根据 drivername 构造 SQLAlchemy URL 字符串（内部复用）

        构造前校验配置可用性：engine 为占位符（完全未配置）时直接抛错，
        避免在连接阶段才报出难懂错误；未知引擎回退纯 engine（交默认方言
        解析），不做拦截

        Returns:
            拼接好的数据库连接 URL 字符串

        Raises:
            ValueError: engine 未配置（占位符）
        """
        if '<' in self.engine:
            raise ValueError(f'engine 未配置（当前值: {self.engine!r}），请先设置 engine 后再访问 url')

        query = self._build_query()
        extra: dict[str, Any] = {'query': query} if query is not None else {}

        if self.is_file_based:
            return URL.create(
                drivername=drivername,
                database=self.file_path or self.name,
                **extra
            ).render_as_string(hide_password=False)

        return URL.create(
            drivername=drivername,
            host=self.host,
            port=self.port,
            username=self.user,
            password=self.password,
            database=self.name,
            **extra
        ).render_as_string(hide_password=False)

    @cached_property
    def url(self) -> str:
        """构造并返回异步驱动版本的数据库 URL 字符串

        Returns:
            异步驱动版本的数据库连接 URL
        """
        return self._create_url(self._build_drivername(self.driver))

    @cached_property
    def sync_url(self) -> str:
        """构造并返回同步驱动版本的数据库 URL 字符串，供 Alembic 等工具使用

        Returns:
            同步驱动版本的数据库连接 URL
        """
        sync_driver = self._SYNC_DRIVERS.get(self._engine_key, self.driver)
        return self._create_url(self._build_drivername(sync_driver))

    # ------------------------------
    # 引擎配置桥接
    # ------------------------------
    def to_node_config(self) -> NodeConfig:
        """转换为 :class:`~fastapi_augment.db.sqlalchemy.engine.NodeConfig`

        桥接规则：
          - ``pool_*`` / ``echo`` / ``url`` 直接映射到同名字段
          - ``connect_timeout`` / ``command_timeout`` 按引擎写入
            ``connect_args``（未定义映射的引擎不写入，避免驱动报错）
          - ``ssl_ca`` / ``ssl_cert`` / ``ssl_key``：mysql 直接作为
            aiomysql 的 connect_args；postgresql 组装为
            ``ssl.SSLContext`` 传给 asyncpg

        Example::

            topology = ClusterTopology(primary=settings.database.to_node_config())
            manager = EngineManager(topology).start()

        Returns:
            可直接用于 ``ClusterTopology`` 的节点配置
        """
        return NodeConfig(
            url=self.url,
            pool_enabled=self.pool_enabled,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=self.pool_pre_ping,
            echo=self.echo,
            connect_args=self._build_connect_args(),
        )

    def _build_connect_args(self) -> dict[str, Any]:
        """按引擎构造 DBAPI connect() 参数（连接超时 / 命令超时 / SSL 证书）

        Returns:
            connect_args 字典；无可用参数时为空字典
        """
        connect_args: dict[str, Any] = {}
        engine = self._engine_key

        if self.connect_timeout > 0:
            key = self._CONNECT_TIMEOUT_KEYS.get(engine)
            if key:
                connect_args[key] = self.connect_timeout

        if self.command_timeout > 0:
            key = self._COMMAND_TIMEOUT_KEYS.get(engine)
            if key:
                connect_args[key] = self.command_timeout

        if engine == 'mysql':
            # aiomysql 原生接受证书路径参数
            if self.ssl_ca:
                connect_args['ssl_ca'] = self.ssl_ca
            if self.ssl_cert:
                connect_args['ssl_cert'] = self.ssl_cert
            if self.ssl_key:
                connect_args['ssl_key'] = self.ssl_key
        elif engine == 'postgresql' and (self.ssl_ca or self.ssl_cert):
            # asyncpg 只接受 ssl.SSLContext 对象
            context = ssl.create_default_context(cafile=self.ssl_ca or None)
            if self.ssl_cert:
                context.load_cert_chain(self.ssl_cert, self.ssl_key or None)
            connect_args['ssl'] = context

        return connect_args
