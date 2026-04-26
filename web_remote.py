"""
Web Remote — serves Performance View to any device on the local network.
Uses aiohttp for HTTP + WebSocket, qrcode for QR generation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
from typing import Optional, List, Dict, Set

from aiohttp import web

logger = logging.getLogger(__name__)

AUTH_COOKIE = "oje_remote_auth"
OP_COOKIE = "oje_remote_operator"


def get_local_ip() -> str:
    """Get the machine's local network IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def generate_qr_data_uri(url: str) -> str:
    """Generate a QR code as a base64 data URI for embedding in HTML."""
    try:
        import qrcode
        import qrcode.image.svg
        import io
        import base64

        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="white", back_color="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except ImportError:
        return ""


class WebRemoteServer:
    """Async web server that streams cue state to connected clients."""

    def __init__(self, port: int = 8080):
        self.port = port
        self.ip = get_local_ip()
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: Set[web.WebSocketResponse] = set()
        self._running = False
        self._operator_names: List[str] = []
        self._remote_password: str = ""
        self._current_state: Dict = {
            "current_cue": None,
            "next_cue": None,
            "countdown": None,
            "timecode": "--:--:--:--",
            "current_group": "",
            "next_group": "",
        }

    @property
    def base_url(self) -> str:
        return f"http://{self.ip}:{self.port}"

    def set_operators(self, names: List[str]):
        self._operator_names = names

    def set_remote_password(self, password: str):
        self._remote_password = password or ""

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def broadcast_state(self, current_cue, next_cue, countdown: Optional[float],
                        timecode: str, current_group: str = "", next_group: str = ""):
        state = {
            "current_cue": _cue_to_dict(current_cue),
            "next_cue": _cue_to_dict(next_cue),
            "countdown": countdown,
            "timecode": timecode,
            "current_group": current_group,
            "next_group": next_group,
        }
        self._current_state = state

        if self._loop and self._clients:
            msg = json.dumps(state)
            self._loop.call_soon_threadsafe(self._broadcast, msg)

    def _broadcast(self, msg: str):
        dead = set()
        for ws in self._clients:
            if ws.closed:
                dead.add(ws)
            else:
                asyncio.ensure_future(ws.send_str(msg), loop=self._loop)
        self._clients -= dead

    def _run_server(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._app = web.Application()
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_post("/auth", self._handle_auth)
        self._app.router.add_post("/logout", self._handle_logout)
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_get("/api/state", self._handle_api_state)

        self._runner = web.AppRunner(self._app)
        self._loop.run_until_complete(self._runner.setup())

        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        self._loop.run_until_complete(site.start())
        logger.info("Web remote started at %s", self.base_url)

        try:
            self._loop.run_forever()
        finally:
            self._loop.run_until_complete(self._runner.cleanup())
            self._loop.close()

    # ── HTTP handlers ────────────────────────────────────────────────────────

    async def _handle_index(self, request):
        operator = request.cookies.get(OP_COOKIE, "")
        html = _render_page(
            operator if operator in self._operator_names else "",
            self._operator_names,
            self.base_url,
            authenticated=self._is_authenticated(request),
            password_required=bool(self._remote_password),
        )
        return web.Response(text=html, content_type="text/html")

    async def _handle_auth(self, request):
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid request."}, status=400)

        password = str(payload.get("password", ""))
        operator = str(payload.get("operator", ""))
        if operator and operator not in self._operator_names:
            return web.json_response({"ok": False, "error": "Unknown operator."}, status=400)
        if self._remote_password and password != self._remote_password:
            return web.json_response({"ok": False, "error": "Wrong password."}, status=403)

        resp = web.json_response({"ok": True})
        resp.set_cookie(AUTH_COOKIE, "1", httponly=False, samesite="Lax")
        resp.set_cookie(OP_COOKIE, operator, httponly=False, samesite="Lax")
        return resp

    async def _handle_logout(self, request):
        resp = web.json_response({"ok": True})
        resp.del_cookie(AUTH_COOKIE)
        resp.del_cookie(OP_COOKIE)
        return resp

    async def _handle_ws(self, request):
        if not self._is_authenticated(request):
            raise web.HTTPUnauthorized(text="Authentication required.")
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)

        await ws.send_str(json.dumps(self._current_state))

        try:
            async for msg in ws:
                pass
        finally:
            self._clients.discard(ws)
        return ws

    async def _handle_api_state(self, request):
        if not self._is_authenticated(request):
            raise web.HTTPUnauthorized(text="Authentication required.")
        return web.json_response(self._current_state)

    def _is_authenticated(self, request) -> bool:
        # No password configured = no auth. The remote loads straight to the
        # cue list, no login overlay — this matches the pre-Codex behaviour
        # operators were used to. Set a remote password in Settings to gate
        # access (the login form is then enforced).
        if not self._remote_password:
            return True
        return request.cookies.get(AUTH_COOKIE) == "1"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cue_to_dict(cue) -> Optional[Dict]:
    if cue is None:
        return None
    return {
        "name": cue.name,
        "description": cue.description,
        "timecode": cue.timecode,
        "color": cue.color,
        "operator_comments": dict(cue.operator_comments) if hasattr(cue, "operator_comments") else {},
    }


def _render_page(
    operator_filter: Optional[str],
    operator_names: List[str],
    base_url: str,
    *,
    authenticated: bool,
    password_required: bool,
) -> str:
    title = f"ØJE CUE MONITOR — {operator_filter}" if operator_filter else "ØJE CUE MONITOR"
    filter_js = json.dumps(operator_filter) if operator_filter else "null"
    operators_js = json.dumps(operator_names)
    authed_js = "true" if authenticated else "false"
    password_required_js = "true" if password_required else "false"
    auth_copy = (
        "Choose operator name and enter the password shown in the Remote window on the Mac, "
        "then tap ENTER REMOTE."
        if password_required
        else "Choose operator name and tap ENTER REMOTE to open the live cue view."
    )
    password_placeholder = "Password from the Mac remote window" if password_required else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{
    height: 100%;
    background: #000;
}}
body {{
    background: #000;
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
    min-height: 100vh;
    min-height: 100svh;
    min-height: 100dvh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    padding-top: env(safe-area-inset-top, 0px);
    padding-right: env(safe-area-inset-right, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
    padding-left: env(safe-area-inset-left, 0px);
}}
.header {{
    background: #0a0a0a;
    padding: 8px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #1a1a1a;
    gap: 12px;
    flex-shrink: 0;
}}
.header-left,
.header-right {{
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
}}
.header .tc {{
    font-family: 'Menlo', 'Courier New', monospace;
    font-size: 14px;
    color: #333;
    flex: 1;
    text-align: center;
    min-width: 0;
}}
.header .clock {{
    font-family: 'Menlo', monospace;
    font-size: 13px;
    color: #444;
}}
.header .title {{
    font-size: 11px;
    color: #444;
    font-weight: bold;
    letter-spacing: 2px;
}}
.main {{
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 24px 32px;
    gap: 16px;
    min-height: 0;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}}
.tag {{
    font-size: 11px;
    color: #4a4a4a;
    font-weight: bold;
    letter-spacing: 3px;
    margin-bottom: 4px;
}}
.group {{
    color: #7a7acd;
    font-size: 13px;
    font-weight: bold;
    margin-left: 12px;
}}
.cue-name {{
    font-size: clamp(28px, 8vw, 64px);
    font-weight: bold;
    line-height: 1.1;
    margin-bottom: 8px;
}}
.cue-desc {{
    font-size: clamp(14px, 3vw, 26px);
    color: #999;
    margin-bottom: 16px;
}}
.operators {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
}}
.op-card {{
    background: #111118;
    border-radius: 8px;
    padding: 12px 16px;
    flex: 1;
    min-width: 150px;
}}
.op-card.solo {{
    min-width: 100%;
}}
.op-name {{
    font-size: 11px;
    color: #7a7acd;
    font-weight: bold;
    letter-spacing: 1px;
    margin-bottom: 4px;
}}
.op-comment {{
    font-size: clamp(16px, 4vw, 28px);
    color: #e6c840;
    word-wrap: break-word;
    white-space: pre-wrap;
}}
.divider {{
    border-top: 1px solid #222;
    margin: 8px 0;
}}
.next-section {{
    padding: 20px 32px;
    background: #050505;
    border-top: 2px solid #1a1a1a;
    flex-shrink: 0;
}}
.next-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
}}
.next-name {{
    font-size: clamp(18px, 4vw, 32px);
    font-weight: bold;
    color: #ccc;
}}
.next-desc {{
    font-size: clamp(12px, 2.5vw, 18px);
    color: #555;
}}
.countdown {{
    font-family: 'Menlo', monospace;
    font-size: clamp(24px, 6vw, 48px);
    font-weight: bold;
    color: #fff;
}}
.countdown.urgent {{
    color: #dc4040;
}}
.next-ops {{
    display: flex;
    gap: 16px;
    margin-top: 8px;
    flex-wrap: wrap;
}}
.next-op {{
    font-size: 14px;
    color: #e6c840;
    font-style: italic;
    white-space: pre-wrap;
}}
.hidden {{ display: none; }}
.overlay {{
    position: fixed;
    inset: 0;
    background: #0a0a0a;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 24px;
    padding-top: max(24px, env(safe-area-inset-top, 0px));
    padding-right: max(24px, env(safe-area-inset-right, 0px));
    padding-bottom: max(24px, env(safe-area-inset-bottom, 0px));
    padding-left: max(24px, env(safe-area-inset-left, 0px));
}}
.auth-card {{
    width: min(420px, 100%);
    background: #111;
    border: 1px solid #2d2d2d;
    border-radius: 12px;
    padding: 24px;
}}
.auth-title {{
    font-size: 18px;
    font-weight: bold;
    margin-bottom: 8px;
}}
.auth-copy {{
    font-size: 13px;
    color: #9a9a9a;
    margin-bottom: 18px;
    line-height: 1.4;
}}
.field {{
    margin-bottom: 14px;
}}
.field label {{
    display: block;
    font-size: 11px;
    color: #7a7a7a;
    font-weight: bold;
    letter-spacing: 2px;
    margin-bottom: 6px;
}}
.field select,
.field input {{
    width: 100%;
    border: 1px solid #333;
    border-radius: 8px;
    background: #050505;
    color: #fff;
    padding: 12px 14px;
    font-size: 15px;
}}
.actions {{
    display: flex;
    gap: 10px;
    margin-top: 18px;
}}
.primary-btn,
.ghost-btn {{
    border: 1px solid #333;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    color: #fff;
    background: #1b1b1b;
}}
.primary-btn {{
    background: #2b5ea7;
    border-color: #2b5ea7;
}}
.error {{
    color: #ff7d7d;
    font-size: 12px;
    min-height: 18px;
}}
.mini-btn {{
    border: 1px solid #2d2d2d;
    border-radius: 999px;
    background: #111;
    color: #858585;
    padding: 4px 10px;
    font-size: 11px;
}}
.connection-lost {{
    position: fixed;
    top: env(safe-area-inset-top, 0px); left: 0; right: 0;
    background: #a03030;
    color: white;
    text-align: center;
    padding: 6px;
    font-size: 12px;
    font-weight: bold;
    z-index: 999;
}}
@media (max-width: 700px) {{
    body {{
        overflow: auto;
    }}
    .header {{
        padding: 8px 12px;
    }}
    .header-left,
    .header-right {{
        gap: 8px;
    }}
    .header .title,
    .header .clock {{
        display: none;
    }}
    .header .tc {{
        text-align: right;
        font-size: 13px;
    }}
    .mini-btn {{
        padding: 4px 8px;
    }}
    .main {{
        justify-content: flex-start;
        padding: 18px 16px;
        gap: 12px;
    }}
    .cue-name {{
        font-size: clamp(24px, 9vw, 40px);
    }}
    .cue-desc {{
        font-size: clamp(14px, 4.2vw, 20px);
        margin-bottom: 10px;
    }}
    .operators {{
        gap: 10px;
    }}
    .op-card {{
        min-width: 100%;
        padding: 10px 12px;
    }}
    .op-comment {{
        font-size: clamp(16px, 5.2vw, 24px);
    }}
    .next-section {{
        padding: 14px 16px calc(14px + env(safe-area-inset-bottom, 0px));
    }}
    .next-row {{
        align-items: flex-start;
        gap: 12px;
    }}
    .next-name {{
        font-size: clamp(18px, 5vw, 26px);
    }}
    .next-desc {{
        font-size: clamp(12px, 3.6vw, 16px);
    }}
    .countdown {{
        font-size: clamp(22px, 8vw, 34px);
    }}
    .next-ops {{
        gap: 8px;
        margin-top: 6px;
    }}
    .next-op {{
        font-size: 13px;
    }}
}}
</style>
</head>
<body>
<div id="conn-banner" class="connection-lost hidden">CONNECTION LOST — RECONNECTING...</div>
<div id="auth-overlay" class="overlay hidden">
    <form class="auth-card" id="auth-form">
        <div class="auth-title">Remote Access</div>
        <div class="auth-copy">{auth_copy}</div>
        <div class="field">
            <label for="operator-select">OPERATOR</label>
            <select id="operator-select" autofocus></select>
        </div>
        <div class="field" id="password-field">
            <label for="password-input">PASSWORD</label>
            <input id="password-input" type="password" autocomplete="current-password" enterkeyhint="go" placeholder="{password_placeholder}">
        </div>
        <div id="auth-error" class="error"></div>
        <div class="actions">
            <button id="auth-submit" class="primary-btn" type="submit">ENTER REMOTE</button>
        </div>
    </form>
</div>

<div class="header">
    <div class="header-left">
        <span class="title">{title.upper()}</span>
        <button id="access-btn" class="mini-btn" type="button">Access</button>
    </div>
    <span class="tc" id="timecode">--:--:--:--</span>
    <div class="header-right">
        <span class="clock" id="clock"></span>
    </div>
</div>

<div class="main" id="current-section">
    <div>
        <span class="tag">CURRENT CUE</span>
        <span class="group" id="cur-group"></span>
    </div>
    <div class="cue-name" id="cur-name">—</div>
    <div class="cue-desc" id="cur-desc"></div>
    <div class="operators" id="cur-ops"></div>
</div>

<div class="next-section">
    <div class="next-row">
        <div>
            <span class="tag">NEXT</span>
            <span class="group" id="next-group"></span>
        </div>
        <div class="countdown" id="countdown"></div>
    </div>
    <div class="next-name" id="next-name">—</div>
    <div class="next-desc" id="next-desc"></div>
    <div class="next-ops" id="next-ops"></div>
</div>

<script>
const OPERATOR_FILTER = {filter_js};
const OPERATOR_NAMES = {operators_js};
const AUTHENTICATED = {authed_js};
const PASSWORD_REQUIRED = {password_required_js};
let ws;
let reconnectTimer;
let currentOperator = OPERATOR_FILTER;

function connect() {{
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(proto + '//' + location.host + '/ws');

    ws.onopen = () => {{
        document.getElementById('conn-banner').classList.add('hidden');
    }};

    ws.onmessage = (event) => {{
        const state = JSON.parse(event.data);
        render(state);
    }};

    ws.onclose = () => {{
        document.getElementById('conn-banner').classList.remove('hidden');
        reconnectTimer = setTimeout(connect, 2000);
    }};

    ws.onerror = () => {{ ws.close(); }};
}}

function render(state) {{
    document.getElementById('timecode').textContent = state.timecode || '--:--:--:--';
    document.getElementById('cur-group').textContent = state.current_group ? '[' + state.current_group + ']' : '';
    document.getElementById('next-group').textContent = state.next_group ? '[' + state.next_group + ']' : '';

    const cur = state.current_cue;
    if (cur) {{
        document.getElementById('cur-name').textContent = cur.name || '—';
        document.getElementById('cur-desc').textContent = cur.description || '';
        renderOps('cur-ops', cur.operator_comments || {{}});
    }} else {{
        document.getElementById('cur-name').textContent = '—';
        document.getElementById('cur-desc').textContent = '';
        document.getElementById('cur-ops').innerHTML = '';
    }}

    const nxt = state.next_cue;
    if (nxt) {{
        document.getElementById('next-name').textContent = nxt.name || '—';
        document.getElementById('next-desc').textContent = nxt.description || '';
        renderNextOps(nxt.operator_comments || {{}});
    }} else {{
        document.getElementById('next-name').textContent = '—';
        document.getElementById('next-desc').textContent = '';
        document.getElementById('next-ops').innerHTML = '';
    }}

    const cd = state.countdown;
    const cdEl = document.getElementById('countdown');
    if (cd !== null && cd !== undefined) {{
        const m = Math.floor(cd / 60);
        const s = Math.floor(cd % 60);
        cdEl.textContent = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
        cdEl.className = cd < 10 ? 'countdown urgent' : 'countdown';
    }} else {{
        cdEl.textContent = '';
    }}
}}

function renderOps(containerId, comments) {{
    const el = document.getElementById(containerId);
    el.innerHTML = '';

    if (currentOperator) {{
        const comment = comments[currentOperator] || '';
        if (comment) {{
            el.innerHTML = '<div class="op-card solo"><div class="op-comment">' +
                escHtml(comment) + '</div></div>';
        }}
    }} else {{
        for (const [name, comment] of Object.entries(comments)) {{
            if (!comment) continue;
            el.innerHTML += '<div class="op-card"><div class="op-name">' +
                escHtml(name) + '</div><div class="op-comment">' +
                escHtml(comment) + '</div></div>';
        }}
    }}
}}

function renderNextOps(comments) {{
    const el = document.getElementById('next-ops');
    el.innerHTML = '';

    if (currentOperator) {{
        const comment = comments[currentOperator] || '';
        if (comment) {{
            el.innerHTML = '<span class="next-op">' + escHtml(comment) + '</span>';
        }}
    }} else {{
        for (const [name, comment] of Object.entries(comments)) {{
            if (!comment) continue;
            el.innerHTML += '<span class="next-op">' + escHtml(name) + ': ' + escHtml(comment) + '</span>';
        }}
    }}
}}

function escHtml(s) {{
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function updateClock() {{
    const now = new Date();
    document.getElementById('clock').textContent =
        String(now.getHours()).padStart(2,'0') + ':' +
        String(now.getMinutes()).padStart(2,'0') + ':' +
        String(now.getSeconds()).padStart(2,'0');
}}

function buildOperatorOptions() {{
    const select = document.getElementById('operator-select');
    select.innerHTML = '<option value="">All Operators</option>';
    for (const name of OPERATOR_NAMES) {{
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        if (name === currentOperator) opt.selected = true;
        select.appendChild(opt);
    }}
}}

async function submitAuth() {{
    const operator = document.getElementById('operator-select').value;
    const password = document.getElementById('password-input').value;
    const errorEl = document.getElementById('auth-error');
    const submitBtn = document.getElementById('auth-submit');
    const overlay = document.getElementById('auth-overlay');
    // Guard against the form firing submit twice (e.g. Enter + click).
    if (submitBtn.disabled) return;
    errorEl.textContent = '';

    // No-password fast path: there's nothing to authenticate against, so
    // skip the /auth roundtrip entirely. Apply the operator filter
    // client-side and hide the overlay. No fetch, no reload, no scope
    // for "the button doesn't do anything" — the user gets instant
    // feedback the moment they tap.
    if (!PASSWORD_REQUIRED) {{
        currentOperator = operator || null;
        overlay.classList.add('hidden');
        return;
    }}

    submitBtn.disabled = true;
    try {{
        const resp = await fetch('/auth', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ operator, password }}),
            credentials: 'same-origin',
        }});
        let data = {{}};
        try {{ data = await resp.json(); }} catch (_e) {{}}
        if (!resp.ok || !data.ok) {{
            errorEl.textContent = data.error || 'Authentication failed.';
            return;
        }}
        currentOperator = operator || null;
        // Reload so the server-rendered page picks up the new auth cookie.
        window.location.reload();
    }} catch (_err) {{
        errorEl.textContent = 'Could not reach the remote server.';
    }} finally {{
        submitBtn.disabled = false;
    }}
}}

function initAuth() {{
    buildOperatorOptions();
    const overlay = document.getElementById('auth-overlay');
    const passwordInput = document.getElementById('password-input');
    const operatorSelect = document.getElementById('operator-select');
    const authForm = document.getElementById('auth-form');
    const authSubmit = document.getElementById('auth-submit');
    document.getElementById('password-field').classList.toggle('hidden', !PASSWORD_REQUIRED);

    // Three paths to submitAuth, all guarded by the submitBtn.disabled
    // double-submit lock so they can't fire twice on the same gesture:
    //   - form submit  → covers Enter inside any text field
    //   - button click → covers tap on iOS where form-implicit-submit
    //                    with only a <select> + hidden input is unreliable
    //   - select keydown Enter → some Safari versions don't bubble
    //                            keydown on a <select> to the form
    authForm.addEventListener('submit', (event) => {{
        event.preventDefault();
        submitAuth();
    }});
    authSubmit.addEventListener('click', (event) => {{
        event.preventDefault();
        submitAuth();
    }});
    operatorSelect.addEventListener('keydown', (event) => {{
        if (event.key === 'Enter' || event.keyCode === 13) {{
            event.preventDefault();
            submitAuth();
        }}
    }});

    document.getElementById('access-btn').addEventListener('click', () => {{
        document.getElementById('auth-error').textContent = '';
        overlay.classList.remove('hidden');
        if (!PASSWORD_REQUIRED) {{
            passwordInput.value = '';
            operatorSelect.focus();
        }} else {{
            passwordInput.focus();
        }}
    }});

    operatorSelect.addEventListener('change', () => {{
        document.getElementById('auth-error').textContent = '';
    }});
    passwordInput.addEventListener('input', () => {{
        document.getElementById('auth-error').textContent = '';
    }});

    if (!AUTHENTICATED) {{
        overlay.classList.remove('hidden');
        if (PASSWORD_REQUIRED) {{
            passwordInput.focus();
        }} else {{
            operatorSelect.focus();
        }}
        return false;
    }}
    overlay.classList.add('hidden');
    return true;
}}

setInterval(updateClock, 1000);
updateClock();
if (initAuth()) {{
    connect();
}}
</script>
</body>
</html>"""
