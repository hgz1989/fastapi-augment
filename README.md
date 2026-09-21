# fastapi-augment

跨项目复用的 FastAPI 通用代码工具包，将多个项目中反复用到的应用工厂、生命周期管理、读写分离数据库层、通用 Mixin、统一响应模型与 HTTP 异常体系统一封装，开箱即用。

## 特性

- **应用工厂** — 一行代码创建 FastAPI 实例，自动装配中间件、路由、生命周期与数据库
- **生命周期管理** — 多注册表、优先级、超时控制、异常策略的启动/关闭钩子
- **读写分离** — 单库 / 主从 / 集群拓扑的异步引擎管理，线程安全的 Session 自动路由
- **泛型仓储** — 类型安全的异步 Repository，支持直接实例化与子类继承两种方式
- **查询解析器** — REST 风格 query string 转 SQLAlchemy 表达式，支持 FIQL 条件、关键字搜索、排序
- **可组合 Mixin** — 时间戳、审计、软删除等列混入，自由组合
- **统一响应** — 全局 `APIResponse` 格式，自动追踪 `request_id`
- **HTTP 异常** — 完整的 4xx 异常子类，内置默认文案
- **OpenAPI 优化** — 自动清理 422 响应与验证错误模型
- **日志管理** — request_id 自动注入、uvicorn 接管、多进程安全轮转、幂等初始化、一键配置
- **健康检查** — 可扩展的检查器模式，内置应用状态与数据库连通性检查，一行开关
- **配置管理** — 基于 pydantic-settings，支持 `.env` 文件、环境变量前缀、嵌套配置
- **数据库迁移 CLI** — 一行命令生成/执行迁移，自动发现用户模型
- **应用发现** — 自动发现子包 `__all__` 导出的 FastAPI 应用，支持排除与导入串校验

## 安装

```bash
pip install fastapi-augment

# 推荐：安装全部可选依赖
pip install fastapi-augment[standard]

# 或按需单独安装
pip install fastapi-augment[sqlalchemy]
pip install fastapi-augment[uvicorn]
pip install fastapi-augment[orjson]
pip install fastapi-augment[config]       # pydantic-settings 配置管理
```

**要求：** Python >= 3.11

## 快速开始

```python
from fastapi import APIRouter
from fastapi_augment import create_app
from fastapi_augment.db.sqlalchemy import (
    ClusterTopology, NodeConfig, EngineManager, SessionFactory,
    ModelBase, RepositoryBase,
)
from fastapi_augment.db.sqlalchemy.mixins import TimestampMixin
from fastapi_augment.schemas import response_success

# ── 1. 数据库拓扑 ──────────────────────────────────────
topology = ClusterTopology(
    primary=NodeConfig(url='postgresql+asyncpg://user:pass@host/db'),
)
manager = EngineManager(topology).start()
sessions = SessionFactory(manager)


# ── 2. 定义模型 ────────────────────────────────────────
class User(TimestampMixin, ModelBase):
    __tablename__ = 'users'
    name: str


# ── 3. 路由 ────────────────────────────────────────────
router = APIRouter()
user_repo = RepositoryBase(User)


@router.get('/users')
async def list_users():
    async with sessions.read_session() as session:
        users = await user_repo.list(session, is_active=True, limit=10)
        return response_success(data=users)


# ── 4. 创建应用 ────────────────────────────────────────
app = create_app(
    title='My Service',
    version='1.0.0',
    engine_manager=manager,
    session_factory=sessions,
    routers=[router],
)
```

## 核心模块

### 应用工厂 — `create_app()`

统一创建 FastAPI 实例，自动装配以下组件：

| 组件     | 说明                                                       |
| -------- | ---------------------------------------------------------- |
| 生命周期 | 接入 `fastapi_lifespan`，合并用户注册表与 `core_registry`  |
| 中间件   | 自动添加 `RequestIdMiddleware`，可选 CORS                  |
| 路由     | 支持 `APIRouter` 列表或 `(router, kwargs)` 元组            |
| OpenAPI  | 自动清理 422 响应与验证错误模型                            |
| 数据库   | 可选挂载 `EngineManager` / `SessionFactory` 到 `app.state` |
| 健康检查 | `health_check=True` 一键启用 `/health` 端点                |

```python
from fastapi_augment import create_app, HookRegistry

registry = HookRegistry()

@registry.on_startup
async def init_cache() -> None:
    ...

app = create_app(
    title='My Service',
    registries=registry,             # 单个或列表均可
    cors_allow_origins=['*'],
    health_check=True,          # 启用健康检查
)
```

### 生命周期 — `HookRegistry`

多注册表、优先级驱动的启动/关闭钩子管理：

```python
from fastapi_augment import HookRegistry

registry = HookRegistry()

# 装饰器语法
@registry.on_startup(priority=100)
async def early_init() -> None: ...

@registry.on_shutdown
async def cleanup() -> None: ...

# 直接注册
registry.register_startup(func, priority=50, timeout=10, abort_on_exception=True)
```

- **优先级** — 数值越大越先执行（启动降序，关闭升序）
- **超时控制** — 可设置单个钩子的超时秒数
- **异常策略** — `abort_on_exception` 控制异常时是否终止流程

### 数据库层 — `db.sqlalchemy`

#### 引擎管理 — `EngineManager`

支持三种部署拓扑：

```python
from fastapi_augment.db.sqlalchemy import ClusterTopology, NodeConfig, EngineManager

# 单库
topology = ClusterTopology(
    primary=NodeConfig(url='postgresql+asyncpg://user:pass@host/db'),
)

# 主从
topology = ClusterTopology(
    primary=NodeConfig(url='postgresql+asyncpg://primary/db'),
    replicas=[NodeConfig(url='postgresql+asyncpg://replica-1/db')],
)

# 集群（主从 + 独立只读节点）
topology = ClusterTopology(
    primary=NodeConfig(url='postgresql+asyncpg://primary/db'),
    replicas=[NodeConfig(url='postgresql+asyncpg://replica-1/db')],
    readonly=[NodeConfig(url='postgresql+asyncpg://readonly-1/db')],
)

manager = EngineManager(topology).start()
# 读引擎轮询（round-robin），线程安全
read_engine = manager.next_read_engine()
```

#### 会话工厂 — `SessionFactory`

读写分离的异步 Session 工厂，支持 FastAPI `Depends()` 注入：

```python
from fastapi_augment.db.sqlalchemy import SessionFactory

sessions = SessionFactory(manager)

# 写会话（自动 commit/rollback）
async with sessions.transaction() as session:
    session.add(obj)
    # 自动 commit

# 读会话（轮询读引擎）
async with sessions.read_session() as session:
    result = await session.execute(select(User))

# FastAPI 依赖注入
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@router.get('/users')
async def list_users(session: AsyncSession = Depends(sessions.depends_read)):
    ...
```

> **缓存说明：** `read_session()` 按 `AsyncEngine` 缓存 `async_sessionmaker`，线程安全，避免重复创建。打印 `SessionFactory` 实例可查看已缓存的引擎信息。

#### 模型基类 — `ModelBase`

基于 ULID 主键的声明式模型基类：

```python
from fastapi_augment.db.sqlalchemy import ModelBase, TimestampMixin

class User(TimestampMixin, ModelBase):
    __tablename__ = 'users'
    name: str
```

#### 泛型仓储 — `RepositoryBase`

类型安全的异步仓储基类，Repository 方法只 **flush**，不 commit，事务边界由调用方控制。
支持两种使用方式：

```python
from fastapi_augment.db.sqlalchemy import RepositoryBase

# 方式 1：直接实例化 — 显式传入模型类
user_repo = RepositoryBase(User)


# 方式 2：子类继承 — 通过泛型参数绑定模型，可扩展自定义方法
class UserRepo(RepositoryBase[User]):
    async def find_by_email(self, session, email: str) -> User | None:
        return await self.get_first(session, email=email)


user_repo = UserRepo()  # 无需再传 User
```

**CRUD 操作：**

```python
# Create（静态方法）
async with sessions.transaction() as session:
    await user_repo.create(session, User(name='alice'))
    await user_repo.create_many(session, [User(name='bob'), User(name='carol')])

# Read（实例方法）
async with sessions.read_session() as session:
    user = await user_repo.get(session, id_='01HXK...')
    user = await user_repo.get_first(session, name='alice')        # 取第一条，无匹配返回 None
    user = await user_repo.get_unique(session, email='a@b.com')   # 精确唯一，多条匹配抛 MultipleResultsFound
    users = await user_repo.list(session, role='admin', order_by=['-created_at'], limit=10)
    total = await user_repo.count(session, is_active=True)
    has_admin = await user_repo.exists(session, role='admin')

# 分页查询（返回 dict：items / page / size / total / pages；size 上限 1000，超限静默截断）
result = await user_repo.paginate(session, page=1, size=10, role='admin', order_by=['-created_at'])
# result = {'items': [...], 'page': 1, 'size': 10, 'total': 100, 'pages': 10}

# Update
async with sessions.transaction() as session:
    await user_repo.update(session, user, name='new_name')
    affected = await user_repo.update_by_id(session, id_='01HXK...', name='new_name')

# Delete
async with sessions.transaction() as session:
    await user_repo.delete(session, user)
    deleted = await user_repo.delete_by_id(session, id_='01HXK...')
    count = await user_repo.delete_where(session, is_active=False)
```

**过滤语法：**

```python
# 关键字过滤 — 等值匹配
await user_repo.list(session, name='alice')

# 序列 — 自动转为 IN 查询
await user_repo.list(session, id_=['01HXK...', '01HXL...'])

# None — 自动转为 IS NULL
await user_repo.list(session, deleted_at=None)

# 原生 SQLAlchemy 表达式
await user_repo.list(session, expressions=(User.age > 18,))

# 排序：字段名前缀 - 表示降序
await user_repo.list(session, order_by=['-created_at', 'name'])
```

### 查询解析器 — `query_parser`

将 REST 风格的 query string 转为 SQLAlchemy `ColumnElement` 条件表达式，可直接传入 `RepositoryBase` 的 `expressions` / `order_by` 参数。

#### where 组合条件（FIQL 风格）

```
where = and_group ("," and_group)*        , 表示 OR
and_group = unit (";" unit)*              ; 表示 AND
unit = "(" where ")" | condition
condition = field OP value
```

**支持的操作符：**

| 语法             | 含义                 | 示例                      |
| ---------------- | -------------------- | ------------------------- |
| `field==value`   | 等于                 | `status==1`               |
| `field!=value`   | 不等                 | `status!=0`               |
| `field~=value`   | 模糊包含 (ILIKE)     | `name~=张`                |
| `field>value`    | 大于                 | `age>18`                  |
| `field>=value`   | 大于等于             | `age>=18`                 |
| `field<value`    | 小于                 | `age<60`                  |
| `field<=value`   | 小于等于             | `age<=60`                 |
| `field~start~end`| 区间 (BETWEEN)       | `age~18~60`               |

```python
from fastapi_augment.db.sqlalchemy import parse_where

# 昵称含张 且 状态非禁用
expr = parse_where('nickname~=张;status!=0', User)

# 括号内 OR，与区间 AND
expr = parse_where('(nickname~=张,username~=王);age~20~30', User)
```

#### lookup 精确匹配

```python
from fastapi_augment.db.sqlalchemy import parse_lookup

# 单字段精确匹配
expr = parse_lookup('phone==13800138000', User, fields={'phone', 'email'})

# 多字段 AND（; 分隔）
expr = parse_lookup('phone==138;status==1', User, fields={'phone', 'status'})
```

#### 关键字搜索

```python
from fastapi_augment.db.sqlalchemy import parse_keyword

# 多字段 OR 模糊搜索
expr = parse_keyword('admin', 'username,email,nickname', User)
```

#### 排序

```python
from fastapi_augment.db.sqlalchemy import parse_sort

# - 前缀表示降序，无前缀为升序
order_by = parse_sort('-created_at,nickname', User)
```

#### 一键组合 — `build_query_expressions`

```python
from fastapi_augment.db.sqlalchemy import build_query_expressions

expressions, order_by = build_query_expressions(
    User,
    where='status!=0;age>=18',
    q='admin',
    q_field='username,nickname',
    sort='-created_at',
)

# 直接传给 paginate / list
result = await user_repo.paginate(
    session, page=1, size=10,
    expressions=expressions, order_by=order_by,
)
```

### 数据库迁移 CLI — `fastapi-augment-migrate`

内置 Alembic 迁移工具，提供 `init` / `generate` / `upgrade` 三个子命令，开箱即用。

#### 快速开始

```bash
# 1. 初始化（一次性操作，生成 alembic.ini + migrations/versions/）
fastapi-augment-migrate init --db-url "sqlite:///test.db"

# 2. 生成迁移
fastapi-augment-migrate generate \
    --message "add_user_table" \
    --models "models,apps.ai.models"

# 3. 执行迁移
fastapi-augment-migrate upgrade
```

#### 初始化 — `init`

在项目根目录生成 `alembic.ini` 和 `migrations/versions/` 目录。
若 `alembic.ini` 已存在则跳过，不会覆盖。

```bash
# 初始化
fastapi-augment-migrate init --db-url "sqlite:///test.db"

# 指定项目根目录
fastapi-augment-migrate init --db-url "postgresql+asyncpg://user:pass@host/db" --project-dir /path/to/project
```

`alembic.ini` 中的 `script_location` 指向库内的 `env.py`，`version_locations` 指向本地 `migrations/versions/`。
`env.py` 通过环境变量 `FASTAPI_AUGMENT_MODELS` 动态导入用户模型，无需手动修改。

#### 生成迁移 — `generate`

通过 `--models` 指定模型模块（逗号分隔），调用 `alembic revision --autogenerate` 生成迁移脚本。
需要先执行 `init` 初始化。

```bash
# 生成迁移
fastapi-augment-migrate generate \
    --message "add_user_table" \
    --models "models,apps.ai.models"

# 指定项目根目录
fastapi-augment-migrate generate \
    --message "add_item" \
    --models "apps.ai.models" \
    --project-dir /path/to/project
```

迁移文件生成在 `<项目根>/migrations/versions/` 目录下。

#### 升级 / 降级 — `upgrade`

`--db-url` 为可选参数，不传时直接从 `alembic.ini` 读取 `sqlalchemy.url`。

```bash
# 升级到最新版本（从 alembic.ini 读取数据库 URL）
fastapi-augment-migrate upgrade

# 指定数据库 URL（覆盖 alembic.ini 中的配置）
fastapi-augment-migrate upgrade --db-url "sqlite:///test.db"

# 升级到指定版本
fastapi-augment-migrate upgrade --revision abc123

# 降级一个版本
fastapi-augment-migrate upgrade --downgrade

# 降级到指定版本
fastapi-augment-migrate upgrade --downgrade --revision abc123

# 指定项目根目录
fastapi-augment-migrate upgrade --project-dir /path/to/project
```

#### CLI 参数一览

| 子命令     | 参数            | 说明                                    |
| ---------- | --------------- | --------------------------------------- |
| `init`     | `--db-url`      | 数据库 URL（默认 `sqlite:///app.db`）   |
|            | `--project-dir` | 项目根目录（默认当前目录）              |
| `generate` | `--message`     | **必填**，迁移描述                      |
|            | `--models`      | **必填**，模型模块路径，逗号分隔        |
|            | `--project-dir` | 项目根目录（默认当前目录）              |
| `upgrade`  | `--db-url`      | 数据库 URL（不传则从 alembic.ini 读取） |
|            | `--revision`    | 目标版本（默认 `head`）                 |
|            | `--downgrade`   | 降级模式                                |
|            | `--project-dir` | 项目根目录（默认当前目录）              |

### 模型 Mixin — `db.sqlalchemy.mixins`

可组合的列混入，按需叠加：

| Mixin                  | 提供的列                                   |
| ---------------------- | ------------------------------------------ |
| `CreatedAtMixin`       | `created_at`                               |
| `TimestampMixin`       | `created_at` + `updated_at`                |
| `CreatedByMixin`       | `created_by`                               |
| `UpdatedByMixin`       | `updated_by`                               |
| `AuditMixin`           | `created_by` + `updated_by`                |
| `SoftDeleteMixin`      | `is_deleted` + `deleted_at`                |
| `SoftDeleteAuditMixin` | `is_deleted` + `deleted_at` + `deleted_by` |

```python
from fastapi_augment.db.sqlalchemy import ModelBase
from fastapi_augment.db.sqlalchemy.mixins import TimestampMixin, SoftDeleteMixin

class User(TimestampMixin, SoftDeleteMixin, ModelBase):
    __tablename__ = 'users'
    name: str
```

### 统一响应 — `schemas`

#### `APIResponse` — 全局返回格式

```json
{
    "request_id": "019xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "code": 0,
    "message": "操作成功",
    "data": { ... },
    "extra": null
}
```

`request_id` 自动从 `ContextVar` 获取，无需手动传递。

#### 工厂函数

```python
from fastapi_augment.schemas import response_success, response_fail

# 成功响应
return response_success(data=user)
return response_success(data=users, extra={'total': 100})

# 失败响应
return response_fail(code=40001, message='用户名已存在')
```

#### 请求参数模型

```python
from fastapi_augment.schemas import PageParams, TimeRangeParams, KeywordParams

# 分页参数
@router.get('/users')
async def list_users(params: PageParams = Depends()):
    ...

# 时间范围 + 关键词搜索
@router.get('/orders')
async def list_orders(
    time_range: TimeRangeParams = Depends(),
    keyword: KeywordParams = Depends(),
):
    ...
```

### HTTP 异常 — `common.exceptions`

完整的 4xx 异常子类，内置默认文案。子类只需声明 `_status_code` 类变量，无需重写 `__init__`：

```python
from fastapi_augment.common.exceptions import (
    BadRequestError,        # 400
    UnauthorizedError,      # 401
    ForbiddenError,         # 403
    NotFoundError,          # 404
    ConflictError,          # 409
    TooManyRequestsError,   # 429（支持 retry_after 参数）
    # ... 更多异常
)

# 使用默认文案
raise NotFoundError()

# 自定义提示
raise BadRequestError(detail='用户名不能为空')

# 限流场景
raise TooManyRequestsError(retry_after=60)
```

### 日志管理 — `logger`

导入即生效：自动注入 `request_id` 到每条日志、接管 uvicorn/fastapi 日志输出。

```python
from fastapi_augment.logger import setup_logger, set_log_level

# 一键配置：控制台 + 按天轮转文件日志
setup_logger(log_dir='./logs', rotation='day', backup_count=30)

# 动态调整日志级别
set_log_level('info')
```

**支持的轮转粒度：**

| 粒度                               | 说明                 |
| ---------------------------------- | -------------------- |
| `'second'` / `'minute'` / `'hour'` | 每整秒/分/点         |
| `'day'`（默认）                    | 每天 00:00           |
| `'week'`                           | 每周一 00:00         |
| `'month'`                          | 每月 1 日 00:00      |
| `'year'`                           | 每年 1 月 1 日 00:00 |

**核心能力：**

- **request_id 注入** — 每条日志自动携带当前请求的 `request_id`，方便链路追踪
- **uvicorn 接管** — 统一 `uvicorn.error` / `uvicorn.access` 的日志名称为 `uvicorn`，屏蔽第三方库 DEBUG 噪声
- **多进程安全** — 日志轮转时捕获 `OSError`（含 `PermissionError`、`FileNotFoundError`），兼容多进程部署（如 `uvicorn --workers N`）
- **幂等初始化** — 重复导入或多次调用 `setup_logger()` 不会叠加处理器或工厂链
- **控制台开关** — `enable_console=False` 可关闭控制台输出，仅保留文件日志

### 健康检查 — `health`

可扩展的检查器模式，内置应用状态与数据库连通性检查。

#### 一行启用

```python
app = create_app(
    title='My Service',
    engine_manager=manager,
    health_check=True,          # 自动注册 /health 端点
)
```

`GET /health` 响应示例：

```json
{
  "status": "healthy",
  "checks": [
    {
      "name": "app",
      "status": "healthy",
      "latencyMs": 0,
      "details": {
        "status": "running",
        "version": "1.0.0",
        "uptimeSeconds": 3600
      }
    },
    { "name": "database", "status": "healthy", "latencyMs": 2.3 }
  ]
}
```

- 总体状态取所有检查项中**最差**的（healthy < degraded < unhealthy）
- 任一检查项 unhealthy 时 HTTP 返回 **503**，便于负载均衡器/探针识别
- 传入 `engine_manager` 时自动包含数据库检查，否则仅检查应用状态

#### 自定义检查器

```python
from fastapi_augment.health import BaseChecker, CheckResult, create_health_router

class RedisChecker(BaseChecker):
    @property
    def name(self) -> str:
        return 'redis'

    async def check(self, app) -> CheckResult:
        # 检查 Redis 连通性
        ...

# 手动注册（适合需要自定义路径或额外检查器的场景）
app.include_router(create_health_router(
    path='/health',
    extra_checkers=[RedisChecker()],
))
```

### 配置管理 — `config`

基于 `pydantic-settings`，支持多种配置来源（环境变量、.env、JSON、YAML、TOML），通过不同类方法加载：

```python
from fastapi_augment.config import AugmentBaseSettings

class Settings(AugmentBaseSettings):
    database_url: str
    redis_url: str = ''
    debug: bool = False
    secret_key: str = 'change-me'

# 从环境变量加载
cfg = Settings.from_env(env_prefix='APP_', env_nested_delimiter='__')

# 从 .env 文件加载
cfg = Settings.from_dotenv('.env', env_prefix='APP_')

# 从 JSON / YAML / TOML 文件加载
cfg = Settings.from_json('config.json')
cfg = Settings.from_yaml('config.yaml')
cfg = Settings.from_toml('config.toml')
```

支持 `SettingsConfigDict` 的所有参数（`env_prefix`、`secrets_dir`、`yaml_file` 等），
与模型字段值自动区分，无需关心分类。

### 中间件 — `middlewares`

#### `RequestIdMiddleware`

自动为每个请求生成/传递 `request_id`（ULID 格式），通过 `ContextVar` 在全链路中可用：

```python
from fastapi_augment.middlewares import get_request_id

request_id = get_request_id()
```

### 应用发现 — `common.app_discovery`

递归发现 `apps` 包下所有子包通过 `__all__` 导出的 FastAPI 应用实例，用于多应用聚合部署与启动前校验。

**约定：** 每个业务子包（如 `apps.platform`）在 `__init__.py` 的 `__all__` 中导出自己创建的 FastAPI 实例（如 `platform_app`）；只有出现在 `__all__` 且确实是 `FastAPI` 实例的对象才被识别为"应用"。

```python
from fastapi_augment.common import discover_fastapi_apps, FastAPIAppSpec, validate_asgi_import

# 发现全部应用（排除主应用，获取主应用之外的其它应用）
apps: list[FastAPIAppSpec] = discover_fastapi_apps(root='apps', exclude='apps.platform:platform_app')

# 每个应用可直接启动（import_string 即 uvicorn 导入串）
for spec in apps:
    uvicorn.run(spec.import_string)   # 'apps.platform:platform_app'

# 启动前校验主应用导入串是否真实存在且为 FastAPI 实例
validate_asgi_import('apps.platform:platform_app')
```

- **`exclude` 支持三种标识** — 模块名（`apps.platform`）、导出名（`platform_app`）或 `module:name` 导入串（`apps.platform:platform_app`）
- 结果按模块名排序，顺序稳定

## 开发与发布

### 分支策略

- **`master`** — 受保护分支，**禁止直接提交代码**，仅可通过其它分支 PR 合并
- **`develop`**（或功能分支）— 日常开发与版本号更新，完成后通过 PR 合并到 `master`
- 发布类操作（Release 打 tag / 上传、PyPI 发布）**仅 `master` 分支可执行**，workflow 已做分支校验

### 代码检查与测试

```bash
# lint（读取 pyproject.toml 的 [tool.ruff] 配置）
uvx ruff check src tests

# 测试
uv run --frozen pytest -q
```

CI 已配置自动检查（`.github/workflows/lint.yml`）：每次 push / PR 自动运行 ruff。

### 发布 Release

`.github/workflows/release.yml` 触发方式：

- **推送到 `master`（自动）** — 本次合并变更了 `VERSION` 时自动发布新版本（打 tag + 上传 GitHub Release）；未变更则跳过，避免重复发布
- **master 分支手动触发**（workflow_dispatch）— `release` 发布新版本 / `rebuild` 重新打包指定版本

发布类操作仅 master 分支可执行，自动完成：

1. **检查** — pytest + ruff，任一失败即停止，不发布
2. **确定版本** — 无 tag 用代码版本（`VERSION` 文件）；代码版本 > 最高 tag 用代码版本；否则以最高 tag 版本为准
3. **校验版本一致性** — 目标版本与代码版本不一致时终止并引导（master 受保护，需先在 `develop` 更新 `VERSION` 与 `factory.py` 版本，PR 合并后重试）
4. **打包** — 源码打包为 `fastapi_augment-<版本>.zip` / `.tar.gz`（排除 `.venv`、缓存、构建产物）
5. **打 tag + 发布** — 打包成功后才创建/更新 `v<版本>` tag 并上传 GitHub Release；失败不留任何 tag/Release，重试不会跳版本

建议发布前先在 `develop` 分支完成版本号更新并 PR 合并到 `master`——合并触发自动发布，发布流程将直接复用代码版本。

PyPI 发布（`.github/workflows/publish.yml`）同样支持合并 `master` 自动触发，仅 `VERSION` 变更时发布（PyPI 版本不可覆盖）。

支持两种模式：

- **release**（默认）— 按版本规则发布新版本
- **rebuild** — 指定已有 tag（如 `v1.2.3`）重新打包上传，不修改代码版本

## 项目结构

```
fastapi_augment/
├── common/
│   ├── app_discovery.py      # FastAPI 应用发现（__all__ 约定）
│   ├── constants.py          # 全局常量与默认错误文案
│   ├── exceptions.py         # 4xx HTTP 异常体系
│   ├── exception_handlers.py # 全局异常处理器
│   └── utils/
│       ├── paths.py          # 路径工具（get_root_dir / find_project_root）
│       └── strings.py        # 字符串工具 / JSON 序列化
├── config/
│   ├── base_settings.py       # AugmentBaseSettings 配置管理
│   └── database_settings.py   # DatabaseSettings 数据库配置
├── db/
│   └── sqlalchemy/
│       ├── engine.py         # EngineManager / NodeConfig / ClusterTopology
│       ├── session.py        # SessionFactory（读写分离）
│       ├── model_base.py     # ModelBase（ULID 主键）
│       ├── repository_base.py # RepositoryBase（泛型仓储 + paginate）
│       ├── query_parser.py    # 查询解析器（where / lookup / keyword / sort）
│       ├── migrate.py        # 数据库迁移 CLI
│       ├── migrations/       # Alembic 迁移环境（env.py / script.py.mako）
│       └── mixins/           # Timestamp / Audit / SoftDelete
├── health/
│   ├── checker.py            # BaseChecker / CheckResult / HealthResponse
│   ├── checkers.py           # AppChecker / DatabaseChecker
│   └── router.py             # create_health_router()
├── logger/
│   ├── record_factory.py     # request_id 注入工厂
│   ├── filters.py            # UvicornNameRewriteFilter
│   ├── handlers.py           # 多进程安全轮转处理器
│   └── setup.py              # setup_logger / set_log_level / set_log_format
├── middlewares/
│   ├── base.py               # BaseASGIMiddleware
│   └── request_id.py         # RequestId 中间件
├── schemas/
│   ├── base.py               # SchemaBase / ORMSchemaBase
│   ├── request.py            # PageParams / TimeRangeParams / KeywordParams
│   ├── response.py           # APIResponse / response_success / response_fail
│   └── pagination.py         # PageData 分页模型
├── factory.py                # create_app 应用工厂
├── lifespan.py               # HookRegistry 生命周期管理
└── openapi.py                # OpenAPI schema 优化
```

## 许可证

MIT
