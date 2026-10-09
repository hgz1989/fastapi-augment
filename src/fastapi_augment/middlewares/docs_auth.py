"""
@Author         : hangu
@CreateDate     : 2026/9/30
@Description    : 文档访问保护中间件（登录页 + 签名 Cookie）

    本方案改为登录页 + 签名 Cookie：
      - 用户名密码仅在登录表单提交时传输一次；
      - 登录成功后下发 HMAC-SHA256 签名的 Cookie（内容不含密码）；
      - Cookie 带有效期（默认会话级，token 内嵌 2 小时兜底），签名防篡改；
      - 之后 /docs /redoc /openapi.json 仅校验 Cookie 签名与有效期。

    登录页路径与受保护路径一一对应（动态推导）：
      访问 /docs         未登录 -> 重定向 /docs/login?next=/docs
      访问 /redoc        未登录 -> 重定向 /redoc/login?next=/redoc
      访问 /openapi.json 未登录 -> 重定向 /openapi.json/login?next=/openapi.json
    登录成功后跳回 next（仅允许受保护路径，防开放重定向）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import time
from urllib.parse import parse_qs, urlsplit

from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .base import BaseASGIMiddleware


class DocsAuthMiddleware(BaseASGIMiddleware):
    """拦截受保护路径（默认 ``/docs /redoc /openapi.json``），未登录则重定向登录页

    登录页路径按受保护路径动态推导（``<受保护路径>/login``）：
      - GET：返回登录表单（携带 next 目标路径）
      - POST：校验用户名密码，成功下发签名 Cookie 并跳转 next（默认 /docs）

    Args:
        app: 下游 ASGI 应用
        credentials: 账号密码列表，每项 ``{"username": "xxx", "password": "xxx"}``；
            支持多个账号，任一账号密码正确即可登录
        secret: Cookie 签名密钥（HMAC-SHA256）。生产环境务必配置随机长密钥；
            未配置时由 ``create_app`` 自动生成，进程重启后所有已发 Cookie 失效
        protected_paths: 需要保护的路径列表；缺省使用默认三条
            （``/docs /redoc /openapi.json``）。由 ``create_app`` 按实际启用的
            ``docs_url / redoc_url / openapi_url`` 传入，支持自定义路径
        title: 应用标题，显示在登录页；缺省时尝试从下游应用读取，再为空串
        summary: 应用摘要，显示在登录页；缺省时尝试从下游应用读取，再为空串
        logo: 登录页顶部 logo（data URI 或 URL）；None 不显示
        cookie_name: Cookie 名称，默认 ``docs_auth``
        max_age: Cookie 有效期（秒）；默认 None 表示**会话级 Cookie**，
            关闭浏览器即失效（Set-Cookie 不含 Max-Age/Expires），token 内嵌
            服务端有效期仍取默认 2 小时作为兜底校验
        cookie_secure: 是否仅 HTTPS 传输 Cookie；生产环境部署 HTTPS 后建议开启

    Example::

        app.add_middleware(DocsAuthMiddleware, credentials=[
            {'username': 'admin', 'password': 'secret'},
            {'username': 'ops', 'password': 'secret2'},
        ], secret='your-secret', protected_paths=['/api-docs', '/openapi.json'])
    """

    # 默认需要保护的路径（精确匹配）；create_app 会按实际配置覆盖
    _DEFAULT_PROTECTED_PATHS: tuple[str, ...] = ('/docs', '/redoc', '/openapi.json')

    # 会话级 Cookie（max_age=None）时 token 内嵌服务端有效期的兜底时长（秒）
    _DEFAULT_TOKEN_TTL: int = 2 * 3600

    def __init__(
            self,
            app: ASGIApp,
            credentials: list[dict[str, str]],
            secret: str,
            protected_paths: list[str] | tuple[str, ...] | None = None,
            title: str | None = None,
            summary: str | None = None,
            logo: str | None = None,
            cookie_name: str = 'docs_auth',
            max_age: int | None = None,
            cookie_secure: bool = False,
    ):
        super().__init__(app)
        # 预构建 username -> password 映射，方便 O(1) 查找
        self._user_map: dict[str, str] = {
            item['username']: item['password'] for item in credentials
        }
        self._protected_paths: tuple[str, ...] = (
            tuple(protected_paths) if protected_paths else self._DEFAULT_PROTECTED_PATHS
        )
        # 登录页路径集合（protected_paths 构造后不可变，预构建避免每请求重建）
        self._login_paths: set[str] = {path + '/login' for path in self._protected_paths}
        self._secret: bytes = secret.encode('utf-8')
        self._cookie_name: str = cookie_name
        self._max_age: int | None = max_age
        self._cookie_secure: bool = cookie_secure
        # 登录页展示的应用信息：优先显式传入，缺省回退下游应用属性
        self._title: str = title or str(getattr(app, 'title', ''))
        self._summary: str = summary or str(getattr(app, 'summary', ''))
        self._logo: str | None = logo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # 覆写基类 __call__：认证拦截需要"短路"（失败时不调用下游），
        # 基类的 on_request/wrap_send/on_finish 钩子模型不适用
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        path = scope.get('path') or ''

        if path in self._login_paths:
            await self._handle_login(scope, receive, send)
            return

        if path in self._protected_paths:
            if self._valid_cookie(scope):
                await self.app(scope, receive, send)
                return
            # 未登录：重定向到对应当前路径的登录页，带 next 回跳目标
            response = RedirectResponse(
                url=f'{path}/login?next={path}',
                status_code=303,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    # ── 登录流程 ───────────────────────────────────────────────────────

    async def _handle_login(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理 ``<受保护路径>/login``：GET 渲染登录页，POST 校验并下发 Cookie

        next 参数（query 或表单）为登录成功后跳转目标，仅允许受保护路径。
        """
        method = (scope.get('method') or 'GET').upper()
        path = scope.get('path') or ''
        # 由登录路径反推目标路径：'/docs/login' -> '/docs'
        protected_path = path[: -len('/login')]

        if method == 'GET':
            next_target = self._safe_next(scope)
            await HTMLResponse(self._login_page(protected_path, next_target))(
                scope, receive, send,
            )
            return

        if method == 'POST':
            # 登录 CSRF 防护：浏览器场景校验 Origin 与请求 Host 同源；
            # 无 Origin 头（curl / 服务端调用）不受此约束
            origin = self._header_value(scope, b'origin')
            if origin:
                host = self._header_value(scope, b'host')
                if not host or urlsplit(origin).hostname != host.split(':')[0]:
                    await PlainTextResponse('Forbidden', status_code=403)(
                        scope, receive, send,
                    )
                    return

            form = await self._read_form(receive)
            username = (form.get('username') or [''])[0]
            password = (form.get('password') or [''])[0]
            next_target = self._safe_next(scope, form)

            expected = self._user_map.get(username)
            if expected is None or not hmac.compare_digest(password, expected):
                await HTMLResponse(
                    self._login_page(protected_path, next_target, error='用户名或密码错误'),
                    status_code=401,
                )(scope, receive, send)
                return

            response = RedirectResponse(url=next_target, status_code=303)
            response.set_cookie(
                self._cookie_name,
                self._make_token(username),
                max_age=self._max_age,
                httponly=True,
                samesite='lax',
                secure=self._cookie_secure,
            )
            await response(scope, receive, send)
            return

        await PlainTextResponse('Method Not Allowed', status_code=405)(scope, receive, send)

    @staticmethod
    def _header_value(scope: Scope, name: bytes) -> str:
        """从请求头中提取指定首部值（不存在返回空串）"""
        for key, value in scope.get('headers') or ():
            if key == name:
                return value.decode('latin-1')
        return ''

    @staticmethod
    async def _read_form(receive: Receive) -> dict[str, list[str]]:
        """读取请求体并按 application/x-www-form-urlencoded 解析为表单字典"""
        body = b''
        while True:
            message = await receive()
            if message['type'] == 'http.request':
                body += message.get('body', b'')
                if not message.get('more_body', False):
                    break
            elif message['type'] == 'http.disconnect':
                break
        return parse_qs(body.decode('utf-8', errors='replace'))

    def _safe_next(self, scope: Scope, form: dict[str, list[str]] | None = None) -> str:
        """解析 next 目标并校验：仅允许受保护路径，非法或缺失回退 /docs"""
        raw = ''
        if form is not None:
            raw = (form.get('next') or [''])[0]
        if not raw:
            query = parse_qs((scope.get('query_string') or b'').decode('latin-1'))
            raw = (query.get('next') or [''])[0]
        return raw if raw in self._protected_paths else '/docs'

    def _login_page(
            self,
            protected_path: str,
            next_target: str,
            error: str | None = None,
    ) -> str:
        """内联登录页 HTML（表单 action 指向当前登录路径，携带 next，展示应用信息）"""
        login_path = protected_path + '/login'
        error_html = (
            f'<p style="color:#c0392b;margin:0 0 12px;">{html.escape(error)}</p>'
            if error else ''
        )
        title_escaped = html.escape(self._title)
        return (
                '<!DOCTYPE html>'
                '<html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Docs登录</title>'
                + (f'<link rel="icon" href="{html.escape(self._logo)}" type="image/png">' if self._logo else '')
                + '<style>'
                'body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
                'background:#f5f6fa;display:flex;align-items:center;justify-content:center;'
                'min-height:100vh;margin:0;}'
                '.card{background:#fff;padding:32px 36px;border-radius:12px;'
                'box-shadow:0 4px 16px rgba(0,0,0,.08);width:340px;}'
                '.header-row{display:flex;align-items:center;gap:12px;justify-content:center;margin:0 0 16px;}'
                '.login-logo{max-height:60px;max-width:120px;object-fit:contain;}'
                'h1{font-size:20px;margin:0;color:#2c3e50;}'
                '.app-summary{margin:-8px 0 16px;color:#667;font-size:13px;text-align:center;}'
                'label{display:block;font-size:13px;color:#555;margin:0 0 6px;}'
                'input{width:100%;box-sizing:border-box;padding:10px 12px;margin:0 0 16px;'
                'border:1px solid #dcdde1;border-radius:6px;font-size:14px;}'
                'input:focus{outline:none;border-color:#3498db;}'
                'button{width:100%;padding:10px 0;background:#3498db;color:#fff;'
                'border:none;border-radius:6px;font-size:15px;cursor:pointer;}'
                'button:hover{background:#2980b9;}'
                '</style></head><body>'
                '<div class="card">'
                # 头部 flex 一行放 logo + h1
                '<div class="header-row">'
                + (f'<img class="login-logo" alt="logo" src="{html.escape(self._logo)}">' if self._logo else '')
                + f'<h1>{title_escaped}</h1>'
                  '</div>'
                + (f'<p class="app-summary">{html.escape(self._summary)}</p>' if self._summary else '')
                + error_html +
                f'<form method="post" action="{login_path}">'
                f'<input type="hidden" name="next" value="{next_target}">'
                '<label for="username">用户名</label>'
                '<input id="username" name="username" type="text" autocomplete="username" required>'
                '<label for="password">密码</label>'
                '<input id="password" name="password" type="password" autocomplete="current-password" required>'
                '<button type="submit">登录</button>'
                '</form></div></body></html>'
        )

    # ── 签名 Cookie ────────────────────────────────────────────────────

    def _make_token(self, username: str) -> str:
        """构造签名 Cookie：base64url(payload) + '.' + HMAC-SHA256 签名

        max_age 为 None（会话级 Cookie）时，token 内嵌的服务端有效期
        仍取默认时长兜底，防止被复制的 Cookie 长期有效
        """
        ttl = self._max_age if self._max_age is not None else self._DEFAULT_TOKEN_TTL
        exp = int(time.time()) + ttl
        payload = json.dumps({'u': username, 'exp': exp}, separators=(',', ':')).encode('utf-8')
        payload_b64 = base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')
        signature = hmac.new(self._secret, payload_b64.encode('ascii'), hashlib.sha256).hexdigest()
        return f'{payload_b64}.{signature}'

    def _valid_cookie(self, scope: Scope) -> bool:
        """校验 Cookie：签名匹配（恒定时间比较）且未过期"""
        token = self._get_cookie(scope)
        if not token or '.' not in token:
            return False

        payload_b64, signature = token.rsplit('.', 1)
        expected = hmac.new(self._secret, payload_b64.encode('ascii'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False

        try:
            padded = payload_b64 + '=' * (-len(payload_b64) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8'))
        except ValueError:
            return False

        exp = data.get('exp')
        return isinstance(exp, int) and exp > time.time()

    def _get_cookie(self, scope: Scope) -> str | None:
        """从请求头解析指定名称的 Cookie 值"""
        headers: list[tuple[bytes, bytes]] = scope.get('headers') or []
        prefix = self._cookie_name + '='
        for name, value in headers:
            if name.lower() == b'cookie':
                for part in value.decode('latin-1').split(';'):
                    part = part.strip()
                    if part.startswith(prefix):
                        return part[len(prefix):]
        return None
