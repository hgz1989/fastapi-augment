# 更新日志

本文件记录 `fastapi-augment` 各版本的变更内容，格式遵循 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.1.5] — 2026-09-21

### Added

- **`common.app_discovery`** — 新增 FastAPI 应用发现模块：
  - `discover_fastapi_apps` — 递归发现 `apps` 子包通过 `__all__` 导出的 FastAPI 应用，支持 `exclude`（模块名 / 导出名 / `module:name` 导入串三种标识），结果按模块名排序
  - `FastAPIAppSpec` — 应用装载信息（模块 / 导出名 / 实例 / `import_string`）
  - `verify_fastapi_app` — 校验 ASGI 应用导入串真实存在且为 FastAPI 实例
- **Release 发布流程** — 新增 `.github/workflows/release.yml` 与配套脚本：
  - 版本决策规则：无 tag 用代码版本 / 代码版本 > 最高 tag 用代码版本 / 否则以最高 tag 版本为准
  - 自动同步 `VERSION` 与 `factory.py` 中 `create_app` 默认版本并提交
  - 源码打包为 zip / tar.gz（排除 `.venv`、缓存、构建产物）
  - 打包成功后才打 tag 并上传 GitHub Release，失败不留任何 tag/Release
  - 支持 release（发布新版本）/ rebuild（重新打包指定版本）两种模式
- **自动 lint** — 新增 `.github/workflows/lint.yml`，push / PR 自动运行 ruff
- **ruff 配置** — `pyproject.toml` 新增 `[tool.ruff]` 规则集（含忽略项中文说明）
- **`find_project_root()`** — 路径工具新增按特征文件（`pyproject.toml` / `.git`）自动定位项目根目录

### Changed

- **性能优化（8 项）**：
  - `SessionFactory` — 缓存命中不再重复创建 sessionmaker
  - `EngineManager.start()` — 幂等，重复启动直接返回；`dispose()` 增加 `_disposed` 状态与 `_ensure_active()` 防护
  - `RepositoryBase._resolve_generic_model` — 改为 classmethod + `lru_cache`
  - `query_parser._convert_value` — 缓存键去掉 `id(column.type)`（id 复用风险）
  - `base_settings._build` — 按 `(cls, config_overrides)` 缓存子类配置
  - `paginate` — 新增 `MAX_PAGE_SIZE = 1000` 上限，超限静默截断
  - `DatabaseSettings._engine_key` — 改为 `cached_property`
- **健壮性（10 项）**：
  - `migrate` — 迁移 CLI 改用 Alembic Python API，失败统一抛 `RuntimeError`
  - `logger.setup` — 移除 `force=True`，不再覆盖宿主日志配置
  - `logger.handlers` — 月 / 年轮转改为时区感知
  - `TooManyRequestsError` — 补回 `status_code` 参数
  - `publish.yml` — 改用 `astral-sh/setup-uv@v6` + `uv sync --group dev`
  - `actions/checkout` — 升级至 v7（安全强化，拦截 Pwn Request）
- **代码风格批量优化**（ruff 全绿）：
  - 59 个文件导入按规范重排（三类分组 / 模块名排序 / from 对象按首次调用顺序 / 括号块末项无逗号）
  - `typing` → `collections.abc`（Sequence / Callable / AsyncGenerator / Mapping / Collection）
  - `int | float` → `float` 注解简化
  - `__all__` 恢复分组注释结构
  - 清理未使用导入、`dict()` → 字面量、合并嵌套 `with`、`raise ... from None` 等

### Fixed

- **测试收集失败** — 重写 `tests/test_database_settings.py`（原草案引用不存在的拓扑设计，改为字段式配置全行为测试）

---

## [0.1.4] — 2026-09-12

### Added

- **`DatabaseSettings`** — 新增独立数据库配置模块，支持多数据库引擎、自动推导驱动/端口、连接池、SSL 等配置
- **`Settings.from_dotenv()`** — 从 .env 文件加载配置
- **`Settings.from_json()`** — 从 JSON 文件加载配置
- **`Settings.from_yaml()`** — 从 YAML 文件加载配置
- **`Settings.from_toml()`** — 从 TOML 文件加载配置

### Changed

- **`EnvSettings` → `AugmentBaseSettings`** — 重命名配置基类，不再局限于环境变量来源，避免与用户自定义 `Settings` 类名冲突
- **`settings.py` → `base_settings.py`** — 重命名配置模块文件，与类名语义对齐
- **`Settings` 重构** — 提取 `_build()` 内部方法统一各来源的配置构建逻辑
- **日志模块** — 目录从 `log` 重命名为 `logger`；`logger/factory.py` → `logger/record_factory.py` 避免与根目录 `factory.py` 混淆
- **`DatabaseSettings` 精简** — 提取 `_create_url()` 公共方法消除 `url`/`sync_url` 重复代码，`_SQLALCHEMY_INSTALL_MSG` 提取为模块级常量
- **代码风格规范化** — 全量对齐项目代码风格规范：
  - 21 个文件移除 docstring/注释结尾句号（约 80 处）
  - 7 个函数/属性补全 `Returns:` 段（`camel_to_snake`、`snake_to_camel`、`random_string`、`BaseChecker.name`、`AppChecker.name`、`DatabaseChecker.name`、`health_check`）
  - `engine.py` `__init__` 移除 `-> None` 返回注解

### Fixed

- **`paginate` 分页计算** — 移除 `pages` 计算中 `if size > 0 else 0` 死代码（`size` 已被 `max(1, size)` 保底）
- **`repository_base`** — `paginate` 入口添加 `page = max(1, page)` / `size = max(1, size)` 边界校验；`list` 方法 `offset`/`limit` 负值防护
- **`random_string`** — 添加 `length < 1` 入口校验，防止静默返回空串
- **`DEFAULT_ERR_MSG`** — 补充 `HTTP_422_UNPROCESSABLE_CONTENT` 状态码，消除 deprecation 警告
- **`openapi.py`** — 异常处理从 `_logger.warning` 升级为 `_logger.exception` 记录完整堆栈
- **`exception_handlers`** — 全部处理器 docstring 句号清除

---

## [0.1.3] — 2026-09-11

### Added

- **查询解析器 `query_parser`** — 新增 REST 风格 query string 转 SQLAlchemy `ColumnElement` 表达式模块
  - `parse_where` — FIQL 风格组合条件，支持 `==` `!=` `~=` `>` `>=` `<` `<=` `~between~` 八种操作符，`;` AND / `,` OR / `()` 括号分组
  - `parse_lookup` — 精确匹配端点过滤器，`;` 分隔多条件 AND，字段白名单 + 防重复校验
  - `parse_keyword` — 多字段 OR 模糊搜索（ILIKE）
  - `parse_sort` — 排序解析，`-field` 降序 / `field` 升序
  - `build_query_expressions` — 一键组合 where + keyword + sort，直接传入 `paginate` / `list` 的 `expressions` / `order_by` 参数
- **`RepositoryBase.get_unique`** — 精确唯一查询，多条匹配时抛出 `MultipleResultsFound`，区别于 `get_first`（取第一条）

### Changed

- **`RepositoryBase`** — `get_one` 拆分为语义更清晰的两个方法：
  - `get_first` — 取第一条匹配记录（`.limit(1)` + `.scalars().first()`），无匹配返回 `None`
  - `get_unique` — 精确唯一匹配，多条匹配抛出异常
- **`create_app()`** — 调整 FastAPI 参数顺序，新增 `summary` 摘要字段支持

### Removed

- **`openapi_enable_bearer_auth`** — 移除 Bearer 认证自动注入功能（`OpenAPICustomConfig` 不再包含 `enable_bearer_auth` / `bearer_auth_name`）

### Fixed

- **`RepositoryBase.__init__`** — 修复初始化时模型类型赋值问题

---

## [0.1.2] — 2026-09-09

### Added

- **`common.utils.paths`** — 新增路径工具函数模块
- **`common.utils` 导出** — `__init__.py` 统一导出路径和字符串工具函数

### Changed

- **构建配置** — 更新 `pyproject.toml` 打包配置

---

## [0.1.1] — 2026-09-07

### Added

- **CI/CD 测试步骤** — `publish.yml` 新增 pytest 测试 Job（Python 3.11 / 3.12 / 3.13 矩阵），发布流程依赖测试通过
- **`test_model_base.py`** — 新增 8 个 `ModelBase` 单元测试
- **`test_settings.py`** — 新增 8 个 `EnvSettings` 配置管理测试
- **`test_migrate.py`** — 新增 10 个数据库迁移 CLI 测试
- **`RepositoryBase` 完整测试** — 46 个测试覆盖 CRUD、过滤、排序、分页、子类继承、异常处理

### Changed

- **`CrudBase` → `RepositoryBase`** — 重命名仓储基类，语义更准确
- **`RepositoryBase` 增强** — 新增 `paginate`、`delete_where`、`update_by_id` 等方法；支持 IN 列表过滤、IS NULL 检查
- **`SessionFactory`** — 优化缓存机制与读写分离逻辑
- **`factory.py`** — 改进 `Any` 类型为 `TYPE_CHECKING` 导入，提升类型安全
- **`db/__init__.py`** — 完善文档注释
- **`README.md`** — 全面重写文档，补充 `WeakKeyDictionary` 注意事项

### Fixed

- **日志处理器** — 修复多进程场景下轮转文件处理器的兼容性问题

---

## [0.1.0] — 2026-09-07

首个公开发布版本。

### 核心模块

| 模块 | 说明 |
| --- | --- |
| `factory.py` | `create_app()` 应用工厂，一行代码创建 FastAPI 实例 |
| `lifespan.py` | `HookRegistry` 生命周期管理，优先级 / 超时 / 异常策略 |
| `db/sqlalchemy/engine.py` | `EngineManager` 异步引擎管理，单库 / 主从 / 集群拓扑 |
| `db/sqlalchemy/session.py` | `SessionFactory` 读写分离会话工厂 |
| `db/sqlalchemy/model_base.py` | `ModelBase` ULID 主键声明式基类 |
| `db/sqlalchemy/crud_base.py` | `CrudBase` 泛型异步仓储基类 |
| `db/sqlalchemy/migrate.py` | `fastapi-augment-migrate` Alembic 迁移 CLI |
| `db/sqlalchemy/mixins/` | `TimestampMixin` / `AuditMixin` / `SoftDeleteMixin` 等可组合 Mixin |
| `schemas/` | `APIResponse` 统一响应、`PageData` 分页模型、请求参数模型 |
| `common/exceptions.py` | 完整 4xx HTTP 异常子类体系 |
| `common/exception_handlers.py` | 全局异常处理器，自动返回标准格式 |
| `log/` | request_id 注入、uvicorn 接管、多进程安全轮转、幂等初始化 |
| `health/` | 可扩展检查器模式，内置应用状态 + 数据库连通性检查 |
| `config/settings.py` | `EnvSettings` 基于 pydantic-settings 的配置管理 |
| `middlewares/` | `RequestIdMiddleware`（ULID 格式），`ContextVar` 全链路传递 |
| `openapi.py` | OpenAPI schema 自动清理 422 响应与验证错误模型 |

[Latest]: https://github.com/hgz1989/fastapi-augment/compare/v0.1.5...develop
[0.1.5]: https://github.com/hgz1989/fastapi-augment/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/hgz1989/fastapi-augment/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/hgz1989/fastapi-augment/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/hgz1989/fastapi-augment/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/hgz1989/fastapi-augment/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hgz1989/fastapi-augment/releases/tag/v0.1.0
