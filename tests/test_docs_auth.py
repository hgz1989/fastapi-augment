"""
@Author         : hangu
@CreateDate     : 2026/9/30
@Description    : DocsAuthMiddleware 中间件测试（登录页 + 签名 Cookie）
                  拦截 /docs /redoc /openapi.json，未登录重定向到对应当前路径的
                  登录页（<路径>/login?next=<路径>）；登录成功后下发 HMAC-SHA256
                  签名 Cookie（含过期时间），并跳回 next 目标
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi_augment import create_app


# ── 工具 ─────────────────────────────────────────────────────────────────

def _make_client(
        credentials: list[dict[str, str]],
        secret: str = 'test-secret',
        *,
        docs_url: str | None = '/docs',
        redoc_url: str | None = '/redoc',
        openapi_url: str | None = '/openapi.json',
) -> TestClient:
    """构造启用 docs 保护的 TestClient"""
    app = create_app(
        docs_credentials=credentials,
        docs_auth_secret=secret,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    return TestClient(app)


def _login(
        client: TestClient,
        username: str,
        password: str,
        login_path: str = '/docs/login',
        next_target: str | None = None,
) -> Any:
    """提交登录表单（不跟随重定向）"""
    data = {'username': username, 'password': password}
    if next_target is not None:
        data['next'] = next_target
    return client.post(login_path, data=data, follow_redirects=False)


def _make_token(username: str, secret: str, *, exp: int | None = None) -> str:
    """手工构造签名 Cookie（与中间件同算法），exp 缺省为当前时间+2小时"""
    if exp is None:
        exp = int(time.time()) + 2 * 3600
    payload = json.dumps({'u': username, 'exp': exp}, separators=(',', ':')).encode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')
    signature = hmac.new(secret.encode('utf-8'), payload_b64.encode('ascii'), hashlib.sha256).hexdigest()
    return f'{payload_b64}.{signature}'


# 受保护路径 → 对应登录页
PROTECTED_PATHS = ('/docs', '/redoc', '/openapi.json')


# ── 登录流程 ─────────────────────────────────────────────────────────────

class TestDocsAuthLoginFlow:

    def test_login_post_rejects_cross_origin(self):
        """跨站 Origin 的登录 POST 返回 403（登录 CSRF 防护）"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = client.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret'},
            headers={'Origin': 'http://evil.example'},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_login_post_allows_same_origin(self):
        """同源 Origin 的登录 POST 正常下发 Cookie（303 跳转）"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = client.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret'},
            headers={'Origin': 'http://testserver'},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_login_page_shows_app_title_and_summary(self):
        """登录页展示 create_app 的 title 与 summary"""
        app = create_app(
            title='My Awesome API',
            summary='业务接口服务',
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
            docs_auth_secret='test-secret',
        )
        client = TestClient(app)
        resp = client.get('/docs/login')
        assert resp.status_code == 200
        assert 'My Awesome API' in resp.text
        assert '业务接口服务' in resp.text

    def test_login_page_shows_logo(self):
        """登录页展示 docs_logo（data URI 内联）"""
        app = create_app(
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
            docs_auth_secret='test-secret',
            docs_logo='data:image/png;base64,AAAA',
        )
        client = TestClient(app)
        resp = client.get('/docs/login')
        assert resp.status_code == 200
        assert '<img class="login-logo"' in resp.text
        assert 'data:image/png;base64,AAAA' in resp.text

    def test_no_logo_no_img(self, monkeypatch):
        """未配置 docs_logo 且包内无 logo.png 时，登录页不渲染 logo"""
        monkeypatch.setattr(
            'fastapi_augment.factory.package_asset_data_uri',
            lambda *args, **kwargs: None,
        )
        app = create_app(
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
            docs_auth_secret='test-secret',
        )
        client = TestClient(app)
        resp = client.get('/docs/login')
        assert resp.status_code == 200
        # 未配置 logo 时不渲染 img 标签（CSS 中的 .login-logo 类名定义始终存在，不断言类名）
        assert '<img class="login-logo"' not in resp.text

    @pytest.mark.parametrize('path', PROTECTED_PATHS)
    def test_unauthenticated_redirects_to_matching_login(self, path: str):
        """未登录访问受保护路径，应重定向到对应当前路径的登录页并带 next"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get('location') == f'{path}/login?next={path}'

    @pytest.mark.parametrize('path', PROTECTED_PATHS)
    def test_login_page_renders_for_each_path(self, path: str):
        """每个受保护路径的登录页均可访问，包含用户名/密码输入框"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = client.get(f'{path}/login')
        assert resp.status_code == 200
        assert 'username' in resp.text and 'password' in resp.text

    @pytest.mark.parametrize('path', PROTECTED_PATHS)
    def test_login_then_access_protected(self, path: str):
        """登录成功后下发 Cookie，可访问所有受保护路径"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = _login(client, 'admin', 'secret', login_path=f'{path}/login')
        assert resp.status_code == 303
        assert resp.headers.get('location') == '/docs'  # 未带 next 时回 /docs
        assert 'docs_auth=' in resp.headers.get('set-cookie', '')

        for target in PROTECTED_PATHS:
            assert client.get(target).status_code == 200

    @pytest.mark.parametrize('path', PROTECTED_PATHS)
    def test_login_redirects_back_to_next(self, path: str):
        """登录成功后跳回 next 目标（访问哪个路径未登录，登录后回哪）"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = _login(
            client,
            'admin',
            'secret',
            login_path=f'{path}/login',
            next_target=path,
        )
        assert resp.status_code == 303
        assert resp.headers.get('location') == path

    def test_unsafe_next_falls_back_to_docs(self):
        """next 仅允许受保护路径，非法值回退 /docs（防开放重定向）"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = _login(client, 'admin', 'secret', next_target='https://evil.com')
        assert resp.status_code == 303
        assert resp.headers.get('location') == '/docs'

    def test_wrong_password_returns_401(self):
        """密码错误重新渲染登录页并返回 401，不下发 Cookie"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = _login(client, 'admin', 'wrong')
        assert resp.status_code == 401
        assert '用户名或密码错误' in resp.text
        assert 'set-cookie' not in resp.headers

    def test_unknown_user_returns_401(self):
        """不存在的用户名返回 401"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = _login(client, 'nobody', 'x')
        assert resp.status_code == 401

    def test_session_cookie_when_max_age_none(self):
        """max_age=None：Set-Cookie 不含 Max-Age/Expires（会话级，关闭浏览器失效）"""
        app = create_app(
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
            docs_auth_secret='test-secret',
            docs_max_age=None,
        )
        client = TestClient(app)
        resp = client.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret', 'next': '/docs'},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        set_cookie = resp.headers.get('set-cookie', '').lower()
        assert 'docs_auth=' in set_cookie
        assert 'max-age=' not in set_cookie
        assert 'expires=' not in set_cookie

    def test_custom_max_age_in_set_cookie(self):
        """max_age=7200：Set-Cookie 带 Max-Age=7200"""
        app = create_app(
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
            docs_auth_secret='test-secret',
            docs_max_age=7200,
        )
        client = TestClient(app)
        resp = client.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret', 'next': '/docs'},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        set_cookie = resp.headers.get('set-cookie', '').lower()
        assert 'max-age=7200' in set_cookie

    def test_session_cookie_token_exp_still_bounded(self):
        """会话级 Cookie 的 token 内嵌 exp 仍按默认 2 小时兜底（服务端校验）"""
        app = create_app(
            docs_credentials=[{'username': 'admin', 'password': 'secret'}],
            docs_auth_secret='test-secret',
            docs_max_age=None,
        )
        client = TestClient(app)
        resp = client.post(
            '/docs/login',
            data={'username': 'admin', 'password': 'secret', 'next': '/docs'},
            follow_redirects=False,
        )
        set_cookie = resp.headers.get('set-cookie', '')
        token = set_cookie.split('docs_auth=', 1)[1].split(';', 1)[0]
        payload_b64, _ = token.rsplit('.', 1)
        padded = payload_b64 + '=' * (-len(payload_b64) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8')
        )
        remaining = payload['exp'] - int(time.time())
        assert 1 * 3600 < remaining <= 2 * 3600

    @pytest.mark.parametrize(
        'username,password',
        [('admin', 'secret1'), ('ops', 'secret2')],
    )
    def test_multiple_accounts_all_can_login(self, username: str, password: str):
        """多账号配置下，任一账号均可登录"""
        client = _make_client([
            {'username': 'admin', 'password': 'secret1'},
            {'username': 'ops', 'password': 'secret2'},
        ])
        resp = _login(client, username, password)
        assert resp.status_code == 303
        assert client.get('/docs').status_code == 200


# ── 自定义路径 ───────────────────────────────────────────────────────────

class TestDocsAuthCustomPaths:

    def test_custom_docs_path_protected(self):
        """自定义 docs_url 时，保护实际启用的路径（如 /api-docs）"""
        client = _make_client(
            [{'username': 'admin', 'password': 'secret'}],
            docs_url='/api-docs',
        )
        resp = client.get('/api-docs', follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get('location') == '/api-docs/login?next=/api-docs'

        assert client.get('/api-docs/login').status_code == 200
        assert _login(client, 'admin', 'secret', login_path='/api-docs/login').status_code == 303
        assert client.get('/api-docs').status_code == 200

    def test_default_path_not_protected_when_customized(self):
        """自定义 docs_url 后，默认 /docs 未注册，不应被中间件拦截"""
        client = _make_client(
            [{'username': 'admin', 'password': 'secret'}],
            docs_url='/api-docs',
        )
        # /docs 无路由 → 404 而非 303，说明中间件未按默认路径保护
        resp = client.get('/docs', follow_redirects=False)
        assert resp.status_code == 404

    def test_disabled_path_not_protected(self):
        """禁用的路径（redoc_url=None）不被保护，其余路径正常保护"""
        client = _make_client(
            [{'username': 'admin', 'password': 'secret'}],
            redoc_url=None,
        )
        # /redoc 无路由 → 404 而非 303
        assert client.get('/redoc', follow_redirects=False).status_code == 404
        # /docs 仍受保护
        assert client.get('/docs', follow_redirects=False).status_code == 303

    def test_all_paths_disabled_no_protection(self):
        """全部文档路径禁用时不挂保护中间件，路径 404 而非 303"""
        client = _make_client(
            [{'username': 'admin', 'password': 'secret'}],
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        assert client.get('/docs', follow_redirects=False).status_code == 404
        assert client.get('/openapi.json', follow_redirects=False).status_code == 404


# ── Cookie 安全 ──────────────────────────────────────────────────────────

class TestDocsAuthCookieSecurity:

    def test_tampered_payload_rejected(self):
        """篡改 Cookie 载荷（签名不匹配）应视为未登录"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        token = _make_token('admin', 'test-secret')
        payload, sig = token.rsplit('.', 1)
        forged = (payload[:-1] + ('A' if payload[-1] != 'A' else 'B')) + '.' + sig
        resp = client.get('/docs', headers={'cookie': f'docs_auth={forged}'}, follow_redirects=False)
        assert resp.status_code == 303

    def test_wrong_secret_rejected(self):
        """用错误密钥生成的 Cookie（签名不匹配）应被拒绝"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        token = _make_token('admin', 'another-secret')
        resp = client.get('/docs', headers={'cookie': f'docs_auth={token}'}, follow_redirects=False)
        assert resp.status_code == 303

    def test_expired_cookie_rejected(self):
        """过期 Cookie 应被拒绝"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        token = _make_token('admin', 'test-secret', exp=int(time.time()) - 100)
        resp = client.get('/docs', headers={'cookie': f'docs_auth={token}'}, follow_redirects=False)
        assert resp.status_code == 303

    def test_garbage_cookie_rejected(self):
        """乱串 Cookie（无分隔符/非法 base64）应被拒绝而非抛异常"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        for token in ('no-separator', '!!!.!!!', 'a' * 100):
            resp = client.get(
                '/docs',
                headers={'cookie': f'docs_auth={token}'},
                follow_redirects=False,
            )
            assert resp.status_code == 303

    def test_invalid_json_payload_rejected(self):
        """payload 是合法 base64 但 JSON 解析失败，应被拒绝而非抛异常"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        raw = base64.urlsafe_b64encode(b'not-json').decode('ascii').rstrip('=')
        signature = hmac.new(
            b'test-secret', raw.encode('ascii'), hashlib.sha256
        ).hexdigest()
        token = f'{raw}.{signature}'
        resp = client.get(
            '/docs',
            headers={'cookie': f'docs_auth={token}'},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_login_path_non_post_rejected(self):
        """登录路径不接受非 POST 方法（如 PUT），返回 405"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        resp = client.put('/docs/login')
        assert resp.status_code == 405

    def test_unprotected_path_not_intercepted(self):
        """非 docs 路径（如根路径）不受中间件影响"""
        client = _make_client([{'username': 'admin', 'password': 'secret'}])
        # 根路径无路由返回 404 而非 303/401，说明未被拦截
        resp = client.get('/')
        assert resp.status_code != 303 and resp.status_code != 401

    def test_no_credentials_disables_protection(self):
        """未配置任何凭证时不启用保护，docs 可正常访问"""
        app = create_app(docs_credentials=None, docs_auth_secret='test-secret')
        client = TestClient(app)
        assert client.get('/docs').status_code == 200


# ── 非 HTTP 请求透传 ────────────────────────────────────────────────────

class TestDocsAuthNonHttp:

    def test_websocket_not_intercepted(self):
        """websocket 请求不受登录保护，直接透传下游（docs_auth 只拦 http）"""
        from starlette.applications import Starlette
        from starlette.routing import WebSocketRoute

        from fastapi_augment.middlewares import DocsAuthMiddleware

        async def ws_endpoint(websocket):
            await websocket.accept()
            await websocket.send_text('ok')
            await websocket.close()

        inner = Starlette(routes=[WebSocketRoute('/ws', ws_endpoint)])
        app = DocsAuthMiddleware(
            inner,
            credentials=[{'username': 'admin', 'password': 'secret'}],
            secret='test-secret',
        )
        client = TestClient(app)

        with client.websocket_connect('/ws') as ws:
            assert ws.receive_text() == 'ok'


# ── 环境变量回退 ─────────────────────────────────────────────────────────

class TestDocsAuthEnvFallback:

    def test_env_multi_credentials(self, monkeypatch: pytest.MonkeyPatch):
        """DOCS_CREDENTIALS 环境变量支持多账号（user1:pass1,user2:pass2）"""
        monkeypatch.setenv('DOCS_CREDENTIALS', 'envuser:envpass,ops:opspass')

        app = create_app(docs_credentials=None, docs_auth_secret='test-secret')
        client = TestClient(app)

        assert client.get('/docs', follow_redirects=False).status_code == 303
        assert _login(client, 'envuser', 'envpass').status_code == 303
        assert client.get('/docs').status_code == 200

        # 第二个账号可重新登录（换 client，避免复用旧 Cookie）
        app2 = create_app(docs_credentials=None, docs_auth_secret='test-secret')
        client2 = TestClient(app2)
        assert _login(client2, 'ops', 'opspass').status_code == 303
        assert client2.get('/docs').status_code == 200

    def test_env_multi_credentials_skips_bad_items(self, monkeypatch: pytest.MonkeyPatch):
        """DOCS_CREDENTIALS 中的空项/缺密码项应被忽略"""
        monkeypatch.setenv('DOCS_CREDENTIALS', 'good:pass,,nopass,')

        app = create_app(docs_credentials=None, docs_auth_secret='test-secret')
        client = TestClient(app)

        assert _login(client, 'good', 'pass').status_code == 303
        # 缺密码项不构成账号
        assert _login(client, 'nopass', 'x').status_code == 401

    def test_env_single_credentials_compat(self, monkeypatch: pytest.MonkeyPatch):
        """DOCS_USERNAME / DOCS_PASSWORD 单账号兼容"""
        monkeypatch.setenv('DOCS_USERNAME', 'envuser')
        monkeypatch.setenv('DOCS_PASSWORD', 'envpass')

        app = create_app(docs_credentials=None, docs_auth_secret='test-secret')
        client = TestClient(app)

        assert client.get('/docs', follow_redirects=False).status_code == 303
        assert _login(client, 'envuser', 'envpass').status_code == 303
        assert client.get('/docs').status_code == 200

    def test_env_secret_is_used(self, monkeypatch: pytest.MonkeyPatch):
        """DOCS_AUTH_SECRET 环境变量作为 Cookie 签名密钥，登录后可正常访问"""
        monkeypatch.setenv('DOCS_CREDENTIALS', 'envuser:envpass')
        monkeypatch.setenv('DOCS_AUTH_SECRET', 'env-secret-key')

        app = create_app(docs_credentials=None)
        client = TestClient(app)

        assert _login(client, 'envuser', 'envpass').status_code == 303
        assert client.get('/docs').status_code == 200

    def test_missing_env_disables_protection(self, monkeypatch: pytest.MonkeyPatch):
        """未配置任何凭证环境变量时不启用保护"""
        monkeypatch.delenv('DOCS_CREDENTIALS', raising=False)
        monkeypatch.delenv('DOCS_USERNAME', raising=False)
        monkeypatch.setenv('DOCS_PASSWORD', 'x')
        monkeypatch.setenv('DOCS_AUTH_SECRET', 'env-secret-key')

        app = create_app(docs_credentials=None)
        client = TestClient(app)
        assert client.get('/docs').status_code == 200
