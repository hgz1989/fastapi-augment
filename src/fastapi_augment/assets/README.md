# assets 资源目录

放置随包分发的静态资源，代码通过 ``fastapi_augment.common.utils.resources``
读取并转为 ``data:`` URI 内联使用（浏览器无法直接访问库安装目录）。

## 当前支持

- ``logo.png``：docs 页面 logo（可选）。放入后自动生效于：
  - ReDoc 顶部（通过 OpenAPI ``info.x-logo`` 扩展，ReDoc 原生支持）
  - docs 登录页（``<受保护路径>/login`` 顶部）
  - **Swagger UI 不支持换 logo**（FastAPI 无对应参数，且不自建 docs 路由）

也可通过 ``create_app(docs_logo=...)`` 显式指定 logo（URL / data URI / 本地路径）。
