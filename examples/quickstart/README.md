# fastapi-augment-quickstart

完整可跑示例项目，展示 `fastapi-augment` 的核心能力与推荐工程模式。
结构沉淀自实际业务项目（browser-proxy），与库文档「快速开始 / 项目配置组合示例」一一对应。

## 快速开始

```bash
# 1. 安装依赖（需 Python >= 3.11）
uv sync --all-groups

# 2. 复制环境变量模板（可选，默认即可运行）
cp .env.example .env

# 3. 启动服务（模块级日志 + 校验 ASGI 导入 + 启动 Uvicorn）
uv run python src/main.py
# 或等价：uv run uvicorn apps.api:app --reload

# 4. 访问
#   API 文档     http://127.0.0.1:8000/docs
#   健康检查     http://127.0.0.1:8000/health
```

试几个接口：

```bash
# 创建商品
curl -X POST http://127.0.0.1:8000/items \
  -H 'Content-Type: application/json' \
  -d '{"name": "示例商品", "price": 9900}'

# 分页查询（默认排除已软删行；加 include_deleted=true 可放开）
curl 'http://127.0.0.1:8000/items?page=1&size=10&include_deleted=false'

# 删除（软删模型自动转软删）
curl -X DELETE http://127.0.0.1:8000/items/{id}

# 聚合（软删模型默认排除已删除行）
curl http://127.0.0.1:8000/items/stats/total
```

## 运行测试

```bash
uv run --group dev pytest -q
```

测试使用**内存 SQLite**，不落盘、不依赖外部服务。

## 目录结构

```
examples/quickstart/
├── pyproject.toml           # hatchling + src 布局；版本号取自 config/settings.py 的 VERSION
├── .env.example             # QUICKSTART_ 前缀环境变量模板
├── src/
│   ├── main.py              # 应用入口：模块级日志（spawn 兼容）+ validate_asgi_import + uvicorn.run
│   ├── config/              # 三段式配置（沉淀自 browser-proxy）
│   │   ├── settings.py          # 全局配置：VERSION（唯一版本源）+ ENV_PREFIX + 日志 + 数据库
│   │   ├── project_settings.py  # 项目元信息：debug / title / summary / version
│   │   └── uvicorn_settings.py  # Uvicorn 运行参数：host / port / asgi_app_ref
│   ├── core/
│   │   └── database.py      # 数据库装配：拓扑 → 引擎 → 会话工厂
│   └── apps/
│       └── api/             # 示例业务子包（通过 __all__ 导出 ASGI 应用）
│           ├── app.py       # 组合根：create_app 装配（生命周期/健康检查/路由）
│           ├── models.py    # Item 模型：TimestampMixin + SoftDeleteMixin
│           ├── schemas.py   # DTO：SchemaBase（请求）/ ORMSchemaBase（响应）
│           └── router.py    # CRUD + 软删除 + 聚合（RepositoryBase）
└── tests/
    ├── conftest.py          # 内存 SQLite 引擎 + 会话工厂 + 应用实例
    └── test_app_api.py      # API 冒烟测试
```

## 展示的能力

| 能力 | 示例位置 | 说明 |
| --- | --- | --- |
| 三段式配置 | `src/config/` | 全局 / 项目 / Uvicorn 三类配置，前缀独立（`QUICKSTART_` / `_PROJECT_` / `_UVICORN_`） |
| 模块级日志 | `src/main.py` | 主进程与 reload/多 worker 子进程（spawn）日志配置一致 |
| 应用工厂 | `apps/api/app.py` | `create_app` 一键装配：生命周期、RequestId 中间件、健康检查、OpenAPI 清理 |
| 生命周期钩子 | `apps/api/app.py` | `HookRegistry` 启动建表、关闭释放连接池 |
| 数据库拓扑 | `src/core/database.py` | `ClusterTopology` + `EngineManager` + `SessionFactory`（读写分离） |
| 泛型仓储 | `apps/api/router.py` | `RepositoryBase` CRUD / 分页 / 聚合 |
| 软删除 | `apps/api/models.py` + router | 查询默认过滤、`include_deleted`、删除自动转软删（`hard_delete_*` 物理删除） |
| 统一响应 | `apps/api/router.py` | `response_success` / `APIResponse`（request_id / code / message / data / extra） |
| 健康检查 | `create_app(health_check=True)` | `/health` 自动包含应用状态 + 数据库连通性 |
| ASGI 校验与发现 | `src/main.py` | `validate_asgi_import` 校验 `apps.api:app`（不限于 FastAPI） |

## 与库文档的对应

- 「快速开始」：`README.md` 顶部示例的完整工程化版本
- 「项目配置组合示例」：`src/config/` 三段式配置的落地实现
- 「数据库层 / 泛型仓储」：`core/database.py` + `apps/api/router.py`
- 「统一响应 / 健康检查」：`apps/api/router.py` + `create_app(health_check=True)`

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `QUICKSTART_DEBUG` | `false` | 全局调试模式（联动 Uvicorn reload） |
| `QUICKSTART_LOGS_DIR` | `./logs` | 日志目录（`null` = 不写文件） |
| `QUICKSTART_LOGS_LEVEL` | `INFO` | 日志级别 |
| `QUICKSTART_DATABASE__ENGINE` | `sqlite` | 数据库引擎 |
| `QUICKSTART_DATABASE__NAME` | `./data/quickstart.db` | SQLite 文件路径 |
| `QUICKSTART_PROJECT_DEBUG` | `false` | 项目调试开关 |
| `QUICKSTART_UVICORN_HOST` | `0.0.0.0` | 监听地址 |
| `QUICKSTART_UVICORN_PORT` | `8000` | 监听端口 |
| `QUICKSTART_UVICORN_WORKERS` | `2` | worker 进程数 |
| `QUICKSTART_UVICORN_ASGI_APP_REF` | `apps.api:app` | 启动的 ASGI 应用引用 |
