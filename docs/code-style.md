# Python 项目代码规范

***

## 1. 注释规范

* 类、函数注释统一使用三双引号（`"""..."""`）Google 风格：`Args:` / `Returns:` / `Raises:` 分段
* 参数、返回值**仅写描述，不写类型**；返回值为 `None` 的方法省略 `Returns:`，其余均须编写
* 所有注释结尾**不使用句号**
* 所有模块必须添加头注释，包含作者、日期、描述；已有头注释仅可修改描述
* 项目头注释模板：

```
"""
@Author         : hangu
@CreateDate     : 2026/9/12
@Description    : <模块职责一句话描述>
"""
```

## 2. 字符串规范

* 普通字符串使用单引号；字符串包含单引号需转义
* 格式化字符串统一使用 f-string；f-string 内部嵌套字符串使用双引号
* 中英文之间不需要空格

## 3. Python 语法版本适配

* 项目 Python ≥3.11：多类型注解使用 `|` 分隔符（`str | None`），空类型直接搭配 None
* 不使用 `Union` / `Optional`

## 4. 导入规范

* 优先使用 `from` 导入；易重名内容使用 `import` 导入
* 导入分三类：标准库、第三方库、项目内部包，组间空行分隔
* 同组内 `import` 导入统一排在 `from` 导入前面，两类语句均按首字母 ASCII 排序
* `from` 语句中，`import` 后的对象严格按照在代码中首次被调用的顺序排列
* 导入对象列表超过 50 字符时，使用 `()` 包裹，括号内每个对象单独一行，最后对象末尾**不加逗号**

## 5. Web 接口规范（按现状）

* 方法使用：GET / POST / PATCH / DELETE（PATCH 用于部分更新）
* 路由内排序：POST（创建类）→ GET（列表 → lookup → 详情）→ PATCH（更新）→ DELETE（撤销）→ 尾部 POST（特殊动作，如 rotate-secret）
* 撤销（软删除）使用 DELETE 接口；逻辑删除保留数据行（delete_reason / deleted_at）

## 6. SQLAlchemy ORM 规范（按现状）

* `mapped_column` 严格按照原生参数顺序编写，参数单独换行
* 最后一个参数不添加尾逗号
* 主键 `id` 由 `fastapi_augment.db.sqlalchemy.ModelBase` 基类提供，模型内不声明主键字段（不写 `sort_order=-10000`）

## 7. ORM 职责规范

* ORM 模型仅保留字段、索引、约束等数据结构相关内容
* 是否可用、是否过期等业务判断逻辑统一放在 Service 层

## 8. Pydantic Schema 字段规范

* 所有字段必须显式使用 `Field` 定义
* Field 参数严格遵循原生函数顺序
* 必填字段不使用 `...`（无默认值即必填），所有字段必须填写描述
* Schema 字段约束与 ORM 模型保持一致
* 数据库唯一性校验等需查库的逻辑，统一在业务层处理

## 9. Schema 命名规范（按现状）

* 模型类名不加 Schema 后缀
* 输入模型使用 `*Request` 后缀（`UserRegisterRequest` / `UserUpdateRequest` / `ApiKeyCreateRequest` / `OAuth2ClientCreateRequest` 等）
* 输出模型使用 `*Out`（`UserOut` / `ApiKeyOut` / `OAuth2ClientOut`）
* 列表响应统一使用 `APIResponse[PageData[XXXOut]]` 分页包装
* 接口参数直接通过 Query / Form 声明，不使用 Params 系列后缀

## 10. 数据访问层规范（按现状）

* 仓储类统一 `XxxRepository` 命名，继承 `fastapi_augment.db.sqlalchemy.RepositoryBase`
* 简单业务场景仅需配置 `model` 属性 + 扩展查询方法
* 不做 CRUD 类（基于 fastapi-augment 框架的 Repository 体系）

## 11. Service 层基础规范（按现状）

* Service 构造函数**无参**，内部实例化 Repository（`self.xxx_repo = XxxRepository(model=Xxx)`）
* 数据库会话由路由层通过 `Depends(get_transaction_session)` 注入并作为方法参数传入
* 服务实例通过依赖注入单例复用（`dependencies/service_deps.py` 的 `@cache` 注入）

## 12. Service 层返回规范（按现状）

* Service 方法返回 ORM 实体；Out 模型转换在 router 层（`XxxOut.model_validate(xxx)`）
* 事务提交由 RepositoryBase 的 create / update 自动处理（或显式 `await session.commit()`），Service 不显式管理 commit
* 认证端点（login / refresh）返回 OAuth2 标准 token 结构，不套统一业务包装；业务接口统一 `APIResponse` / `response_success` 包装

## 13. API 注入规范

* 接口统一使用 `Annotated[T, Depends(xxx)]` 完成依赖注入

## 14. API 参数规范（按现状）

* 路径参数：裸声明 + 类型注解（`user_id: str`），不使用 `Path(alias=...)`
* 查询参数：统一使用 `Query(...)`
* 表单参数：统一使用 `Form(...)`（OAuth2 登录 / 刷新表单）

## 15. API 缓存规范（按现状）

* 当前无接口级缓存体系（无 CacheManager）
* 认证热路径使用 `infrastructure/cache.py` 的 `TTLCache`（TTL 60 秒）：
  * API Key 认证结果缓存（防重复查库）
  * `last_used` 更新节流（TouchThrottle）
* 未来引入接口级缓存时，缓存键格式 `{接口路径}_{请求参数}`、默认 TTL 10 秒、JSON 字符串编码

## 16. __init__.py 规范

* `__init__.py` 只导出同级模块文件内的类、函数、变量、常量等需要导出的内容
* 不引入跨层 / 跨模块的间接导出

## 17. 类、函数规范

* 类的 `__init__` 方法不写 `-> None`
* 所有方法、函数参数都需要添加类型注解

## 18. 包管理

* Python 包管理统一使用 uv

## 19. 代码检查与测试

* 代码风格检查统一使用 ruff，规则配置在 `pyproject.toml` 的 `[tool.ruff]`
* 提交 / 合并前必须 `ruff check src tests` 全绿
* 提交 / 合并前必须 `uv run --frozen pytest -q` 全量测试通过
* CI 已配置 `lint.yml`（push / PR 自动 lint），发布前在 `publish.yml` / `release.yml` 中再次复查

## 20. 版本管理

* 版本号以仓库根目录 `VERSION` 文件为唯一来源，`pyproject.toml` 通过 `version = { file = "VERSION" }` 动态读取
* 发布时同步更新 `factory.py` 中 `create_app` 的默认版本参数，保持与 `VERSION` 一致
* 版本变更记录统一维护在根目录 `CHANGELOG.md`（Keep a Changelog 格式）
