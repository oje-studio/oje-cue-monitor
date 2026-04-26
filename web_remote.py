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
            "fps": 25.0,
            "db": -120.0,
            "signal_ok": False,
            "running": False,
            "signal_warning": "",
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
                        timecode: str, current_group: str = "", next_group: str = "",
                        fps: float = 25.0, db: float = -120.0,
                        signal_ok: bool = False, running: bool = False,
                        signal_warning: str = ""):
        state = {
            "current_cue": _cue_to_dict(current_cue),
            "next_cue": _cue_to_dict(next_cue),
            "countdown": countdown,
            "timecode": timecode,
            "current_group": current_group,
            "next_group": next_group,
            # Mirror what the operator sees on the Mac's Performance bar so
            # the web view can show the same status at a glance.
            "fps": float(fps),
            "db": float(db),
            "signal_ok": bool(signal_ok),
            "running": bool(running),
            "signal_warning": str(signal_warning or ""),
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
        # How operator filter is resolved depends on whether a password
        # is configured for the remote:
        #   * Password mode: trust OP_COOKIE (set by the /auth flow on
        #     successful login). The user has already paid the cost of
        #     entering a password and picking an operator; honour that
        #     across reloads. To switch operator they use Access on
        #     desktop or log out.
        #   * No-password mode: ignore the cookie. Every reload starts
        #     with an empty filter, JS shows the picker, and the user
        #     re-confirms who they are. This matches the operator's
        #     expectation that a reload = a fresh "who am I" prompt.
        if self._remote_password:
            op = request.cookies.get(OP_COOKIE, "").strip()
            operator = op if op in self._operator_names else ""
        else:
            operator = ""
        html = _render_page(
            operator,
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
html, body {{
    background: #000;
    /* iOS Safari ignores overflow:hidden on body for touch scrolling —
       the page still rubber-bands left/right/up/down when the finger
       drags. position:fixed + inset:0 + overscroll-behavior:none locks
       it down properly. Anything that needs to scroll (.main) does so
       inside its own box, not by moving the whole page. */
    position: fixed;
    inset: 0;
    overflow: hidden;
    overscroll-behavior: none;
    /* Block accidental two-finger zoom / pinch on the chrome but allow
       inner scroll regions to handle their own gestures. */
    touch-action: pan-y;
    -webkit-tap-highlight-color: transparent;
}}
body {{
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
    /* svh = "smallest viewport height" — the slice of screen that's
       always visible, even when iOS Safari's toolbar is up. Using it
       guarantees the bottom strip never lands under the URL bar. */
    height: 100vh;
    height: 100svh;
    /* Three-row grid: top status bar, flexible main, bottom strip.
       No flex-shifting when cue text changes length between updates. */
    display: grid;
    grid-template-rows: auto 1fr auto;
    grid-template-columns: 100%;
    /* Honour notch / home-indicator. Padding lives inside the box-sizing
       so we never exceed 100 % width and never trigger horizontal scroll. */
    padding-top: env(safe-area-inset-top, 0px);
    padding-right: env(safe-area-inset-right, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
    padding-left: env(safe-area-inset-left, 0px);
}}

/* ── Top status bar (mirrors Performance Mode) ──────────────────────────── */
.statusbar {{
    background: #0a0a0a;
    border-bottom: 1px solid #1a1a1a;
    padding: 10px 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    flex-wrap: nowrap;
    min-height: 54px;
    overflow: hidden;
    /* Single rule for every text item in the bar — same font, weight,
       size and letter-spacing across TC / FPS / state / dB / clock so
       the row looks rhythmic instead of mismatched. Each item still
       has its own colour via its specific class below. */
    font-family: 'Menlo', 'SF Mono', 'Courier New', monospace;
    font-size: clamp(16px, 4vw, 22px);
    font-weight: 800;
    letter-spacing: 0.5px;
}}
.statusbar > * {{ white-space: nowrap; }}
.statusbar .dot {{
    color: #d75a5a;
    line-height: 1;
}}
.statusbar .dot.ok {{ color: #4bc373; }}
.statusbar .tc {{
    color: #f0f0f0;
    /* Reserve max width for HH:MM:SS:FF so the bar doesn't reflow when
       the value goes from "--" to "10:00:00:00". */
    min-width: 9.5ch;
    text-align: center;
}}
.statusbar .meta {{ color: #858585; }}
.statusbar .clock {{
    color: #dcdcdc;
    min-width: 8ch;
    text-align: center;
}}
.statusbar .sep {{ color: #3d3d3d; }}

/* ── 5-bar VU meter (CSS only, mirrors the Mac one) ─────────────────────── */
.vu {{
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 18px;
}}
.vu .bar {{
    width: 10px;
    height: 100%;
    border-radius: 1px;
    background: #1a3320;          /* dark green when unlit */
}}
.vu .bar:nth-child(4) {{ background: #37280f; }}     /* amber slot, unlit */
.vu .bar:nth-child(5) {{ background: #3c1414; }}     /* red slot, unlit */
.vu .bar.lit:nth-child(-n+3) {{ background: #4bc373; }}
.vu .bar.lit:nth-child(4)    {{ background: #e18730; }}
.vu .bar.lit:nth-child(5)    {{ background: #d74b4b; }}

/* ── Main current-cue area — fills remaining height ──────────────────────── */
.main {{
    background: #090909;
    padding: 22px clamp(20px, 6vw, 64px);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 0;
}}
.tag-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    color: #4a4a4a;
}}
.tag {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 3px;
}}
.group {{
    color: #7a7acd;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}}
.cue-name {{
    /* clamp lets it scale on phones (28px) up to a reasonable 64 on a
       laptop without rampaging on a 4 K display. */
    font-size: clamp(28px, 7vw, 64px);
    font-weight: 800;
    line-height: 1.05;
    color: #ffffff;
}}
.cue-desc {{
    font-size: clamp(14px, 2.6vw, 22px);
    color: #999999;
    line-height: 1.35;
}}
.operators {{
    display: grid;
    /* auto-fit so 1/2/3+ operators tile naturally; minmax keeps each
       card readable on phone. */
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 10px;
    margin-top: 4px;
}}
.op-card {{
    background: #111118;
    border-radius: 8px;
    padding: 12px 14px;
    border: 1px solid #1c1c25;
}}
.op-name {{
    font-size: 10px;
    color: #7a7acd;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 4px;
}}
.op-comment {{
    font-size: clamp(15px, 3vw, 22px);
    color: #e6c840;
    word-wrap: break-word;
    white-space: pre-wrap;
    line-height: 1.35;
}}

/* ── Bottom: Next cue strip ──────────────────────────────────────────────── */
.next-strip {{
    background: #050505;
    border-top: 2px solid #1a1a1a;
    padding: 16px clamp(20px, 5vw, 40px);
    display: grid;
    grid-template-columns: 1fr auto;
    column-gap: 16px;
    align-items: center;
    /* Reserve a stable height (so the main area doesn't grow when the
       show ends) AND cap it (so unusually long content can never push
       its own tail under iOS Safari's bottom chrome). */
    min-height: 78px;
    max-height: 30vh;
    overflow: hidden;
}}
.next-info {{ min-width: 0; }}
.next-tag {{
    font-size: 10px;
    color: #4a4a4a;
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 2px;
}}
.next-name {{
    font-size: clamp(16px, 3.6vw, 26px);
    font-weight: 700;
    color: #cccccc;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.next-desc {{
    font-size: clamp(11px, 2vw, 15px);
    color: #555555;
    margin-top: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.countdown {{
    font-family: 'Menlo', monospace;
    font-size: clamp(24px, 5.5vw, 40px);
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.5px;
    /* Reserve enough width for "in MM:SS" so layout doesn't twitch
       when countdown changes from 9 to 10 seconds. */
    min-width: 7ch;
    text-align: right;
}}
.countdown.urgent {{ color: #dc4040; }}
.next-ops {{
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 6px;
}}
.next-op {{
    font-size: clamp(11px, 2.2vw, 14px);
    color: #e6c840;
    font-style: italic;
    white-space: pre-wrap;
}}
.hidden {{ display: none !important; }}
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
/* Floating Access pill — sits in the top-right corner over the status
   bar without occupying flex space, so the status bar stays a single
   tight row on phones. */
.access-pill {{
    position: fixed;
    top: calc(env(safe-area-inset-top, 0px) + 8px);
    right: calc(env(safe-area-inset-right, 0px) + 12px);
    border: 1px solid #2d2d2d;
    border-radius: 999px;
    background: rgba(20, 20, 20, 0.9);
    color: #b5b5b5;
    padding: 4px 12px;
    font-size: 11px;
    z-index: 50;
    cursor: pointer;
}}
.access-pill:hover {{ background: rgba(35, 35, 35, 0.95); }}
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
/* Phone-specific tweaks. The base layout is already mobile-first via
   clamp() and grid auto-fit, this just trims spacing on small screens. */
@media (max-width: 600px) {{
    .statusbar {{
        padding: 8px 10px;
        gap: 6px;
        min-height: 44px;
        font-size: 14px;     /* uniform shrink for every text item */
    }}
    .statusbar .sep,
    .statusbar #fps,
    .statusbar #signal-db {{
        display: none;       /* keep TC + state + VU + clock — drop FPS, dB text, separators */
    }}
    .statusbar .tc {{ min-width: 0; }}
    .statusbar .clock {{ min-width: 0; }}
    .vu {{ height: 14px; gap: 1px; }}
    .vu .bar {{ width: 7px; }}
    /* Hide Access on phones — it overlapped the clock on the right.
       Operators on phone can lock to a specific operator via the URL
       parameter (e.g. http://192.168.0.x:8080/?op=Lighting), so the
       picker UI isn't strictly needed in this view. */
    .access-pill {{ display: none; }}
    .main {{
        padding: 16px;
        gap: 8px;
    }}
    .next-strip {{
        padding: 10px 14px;
        min-height: 60px;
    }}
    /* On phones, hide the next-cue operator notes — they push the
       strip beyond the bottom safe area when several operators have
       long comments. The operator looks at notes for the *current*
       cue; for "next" the name + countdown is enough preview. */
    .next-ops {{ display: none; }}
    .operators {{
        grid-template-columns: 1fr;     /* one card per row on phone */
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

<!-- Top status bar — same shape as the Performance Mode header. -->
<div class="statusbar">
    <span class="dot" id="signal-dot">●</span>
    <span class="tc" id="timecode">--:--:--:--</span>
    <span class="sep">|</span>
    <span class="meta" id="fps">FPS --</span>
    <span class="sep">|</span>
    <span class="meta" id="signal-state">NO SIGNAL</span>
    <span class="sep">|</span>
    <span class="vu" id="vu" aria-label="Audio level">
        <span class="bar"></span>
        <span class="bar"></span>
        <span class="bar"></span>
        <span class="bar"></span>
        <span class="bar"></span>
    </span>
    <span class="meta" id="signal-db">−∞ dB</span>
    <span class="sep">|</span>
    <span class="clock" id="clock">--:--:--</span>
</div>
<!-- Access button floats over the status bar so it doesn't push the bar
     into a two-row layout on narrow screens. -->
<button id="access-btn" class="access-pill" type="button">Access</button>

<!-- Current cue — owns the flexible row. -->
<div class="main">
    <div class="tag-row">
        <span class="tag">CURRENT CUE</span>
        <span class="group" id="cur-group"></span>
    </div>
    <div class="cue-name" id="cur-name">—</div>
    <div class="cue-desc" id="cur-desc"></div>
    <div class="operators" id="cur-ops"></div>
</div>

<!-- Next cue strip — pinned to bottom, fixed minimum height. -->
<div class="next-strip">
    <div class="next-info">
        <div class="next-tag">NEXT &nbsp;<span class="group" id="next-group"></span></div>
        <div class="next-name" id="next-name">—</div>
        <div class="next-desc" id="next-desc"></div>
    </div>
    <div class="countdown" id="countdown"></div>
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

    // ── Status bar ──
    // Signal dot + state text mirror Performance Mode's three-state UI:
    //   running + signal_ok    → green, "LIVE"
    //   running + no signal    → red,   "NO SIGNAL"
    //   not running             → grey,  "OFF"
    const dot = document.getElementById('signal-dot');
    const stateLbl = document.getElementById('signal-state');
    if (!state.running) {{
        dot.className = 'dot';
        dot.style.color = '#3d3d3d';
        stateLbl.textContent = 'OFF';
        stateLbl.style.color = '#555';
    }} else if (state.signal_ok) {{
        dot.className = 'dot ok';
        dot.style.color = '';
        stateLbl.textContent = state.signal_warning || 'LIVE';
        stateLbl.style.color = state.signal_warning ? '#e6c840' : '#4bc373';
    }} else {{
        dot.className = 'dot';
        dot.style.color = '';
        stateLbl.textContent = 'NO SIGNAL';
        stateLbl.style.color = '#d75a5a';
    }}

    // FPS
    const fps = state.fps;
    document.getElementById('fps').textContent =
        (typeof fps === 'number' && fps > 0) ? 'FPS ' + fps.toFixed(2) : 'FPS --';

    // dB level + VU meter (5 bars, same mapping as the Mac meter:
    //   -60 dBFS → 0 lit, 0 dBFS → 5 lit, last bar = clip indicator)
    const db = state.db;
    const dbEl = document.getElementById('signal-db');
    const vuBars = document.querySelectorAll('#vu .bar');
    let lit = 0;
    if (typeof db === 'number' && db > -120) {{
        dbEl.textContent = (db >= 0 ? '+' : '') + db.toFixed(1) + ' dB';
        dbEl.style.color = db > -3 ? '#d75a5a' : (db > -12 ? '#e6c840' : '#dcdcdc');
        const norm = Math.max(0, Math.min(1, (db + 60) / 60));
        lit = Math.round(norm * vuBars.length);
    }} else {{
        dbEl.textContent = '−∞ dB';
        dbEl.style.color = '#7a7a7a';
    }}
    vuBars.forEach((b, i) => b.classList.toggle('lit', i < lit));

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
    // client-side, hide the overlay, and open the WS if we haven't
    // already (initAuth defers connect when the picker is shown).
    if (!PASSWORD_REQUIRED) {{
        currentOperator = operator || null;
        overlay.classList.add('hidden');
        if (!ws || ws.readyState >= WebSocket.CLOSING) {{
            connect();
        }}
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

    // Authenticated path:
    //   * Password mode: /auth has already happened — don't ask again on
    //     reload, even if the operator field was left as "All Operators".
    //     Re-showing the picker here would create a loop, because
    //     submitAuth in password mode requires a password the user
    //     no longer has on screen.
    //   * No-password mode: ask for operator on every reload. submitAuth
    //     takes the no-password fast path (no /auth, no password needed).
    if (!OPERATOR_FILTER && !PASSWORD_REQUIRED) {{
        overlay.classList.remove('hidden');
        operatorSelect.focus();
        return false;     // wait for ENTER REMOTE → submitAuth → connect()
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
