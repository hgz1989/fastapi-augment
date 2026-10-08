"""
@Author         : hangu
@CreateDate     : 2026/9/30
@Description    : fastapi-augment 单文件 Demo —— 基础应用部分

    配置使用包内 settings 模块（AugmentBaseSettings.from_dotenv）：
      - 优先读取同目录 .env（DEMO_ 前缀），如 examples/.env
      - 环境变量优先级高于 .env（如 set DEMO_DOCS_ACCOUNTS=demo:secret123）
      - 未配置 .env 时使用默认值运行（docs 保护自动关闭）

运行（主项目 venv，无需独立项目/依赖安装）：
    .venv\\Scripts\\python.exe examples\\demo.py
    或
    uv run python examples\\demo.py

访问：
    Swagger UI   http://127.0.0.1:8000/docs        （配置了账号密码时需先登录）
    健康检查     http://127.0.0.1:8000/health
    业务接口     http://127.0.0.1:8000/hello?name=world

docs 登录（配置了 DEMO_DOCS_ACCOUNTS 时）：
    - 访问 /docs 未登录 -> 跳转 /docs/login，访问 /redoc -> /redoc/login，
      /openapi.json -> /openapi.json/login；登录成功后跳回原路径
    - 账号格式 user1:pass1,user2:pass2，支持多账号
    - 签名密钥 DEMO_DOCS_SECRET 缺失时自动随机生成（重启后需重新登录）
    - logo：DEMO_DOCS_LOGO 配置 URL/路径，或放包内 assets/logo.png 自动生效
      （ReDoc 顶部 + 登录页；Swagger 不支持换 logo）
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field

from fastapi_augment import create_app
from fastapi_augment.schemas import response_success
from fastapi_augment.settings import AugmentBaseSettings


# ── 配置：从 examples/.env 读取（DEMO_ 前缀），环境变量优先 ───────────────
class DemoSettings(AugmentBaseSettings):
    """Demo 应用配置：.env / 环境变量均可覆盖"""

    title: str = Field(
        default='fastapi-augment Demo',
        description='应用标题',
        examples=['fastapi-augment Demo'],
    )
    summary: str = Field(
        default='单文件基础应用示例',
        description='应用摘要',
        examples=['单文件基础应用示例'],
    )
    version: str = Field(
        default='0.1.0',
        description='应用版本号',
        examples=['0.1.0'],
    )
    docs_accounts: str | None = Field(
        default=None,
        description='Docs 登录账号列表，格式 user1:pass1,user2:pass2；配置后 /docs /redoc /openapi.json 需登录',
        examples=['demo:secret123,ops:secret456'],
    )
    docs_secret: str | None = Field(
        default=None,
        description='Docs 登录 Cookie 签名密钥（HMAC-SHA256）；缺省时随机生成',
        examples=['a-random-long-secret'],
    )
    docs_logo: str | None = Field(
        default=None,
        description='Docs 页面 logo（URL / data URI / 本地路径）；缺省时尝试包内 assets/logo.png',
        examples=['https://example.com/logo.png'],
    )


settings = DemoSettings.from_dotenv(
    Path(__file__).resolve().parent / '.env',
    env_prefix='DEMO_',
)

# ── 应用装配：基础参数 + 健康检查 + docs 登录保护 ────────────────────────
docs_credentials = []
if settings.docs_accounts:
    for item in settings.docs_accounts.split(','):
        item = item.strip()
        if not item or ':' not in item:
            continue
        username, password = item.split(':', 1)
        username, password = username.strip(), password.strip()
        if username and password:
            docs_credentials.append({'username': username, 'password': password})
docs_credentials = docs_credentials or None

app = create_app(
    title=settings.title,
    summary=settings.summary,
    version=settings.version,
    debug=False,
    health_check=True,
    docs_credentials=docs_credentials,
    docs_auth_secret=settings.docs_secret,
    docs_logo=settings.docs_logo,
    docs_max_age=None
)


# ── 业务路由：统一 APIResponse 格式 ────────────────────────────────────────
@app.get('/hello')
async def hello(name: str = 'world'):
    """基础接口，返回统一响应：{"code": 0, "message": "操作成功", "data": {...}, ...}"""
    return response_success(data={'message': f'Hello, {name}!'})


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='127.0.0.1', port=8000)
