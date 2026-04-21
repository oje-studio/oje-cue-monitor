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
        self._app.router.add_get("/operator/{name}", self._handle_operator)
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
        html = _render_page(None, self._operator_names, self.base_url)
        return web.Response(text=html, content_type="text/html")

    async def _handle_operator(self, request):
        name = request.match_info["name"]
        html = _render_page(name, self._operator_names, self.base_url)
        return web.Response(text=html, content_type="text/html")

    async def _handle_ws(self, request):
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
        return web.json_response(self._current_state)


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


def _render_page(operator_filter: Optional[str], operator_names: List[str], base_url: str) -> str:
    title = f"ØJE CUE MONITOR — {operator_filter}" if operator_filter else "ØJE CUE MONITOR"
    filter_js = json.dumps(operator_filter) if operator_filter else "null"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #000;
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}}
.header {{
    background: #0a0a0a;
    padding: 8px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #1a1a1a;
}}
.header .tc {{
    font-family: 'Menlo', 'Courier New', monospace;
    font-size: 14px;
    color: #333;
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
}}
.divider {{
    border-top: 1px solid #222;
    margin: 8px 0;
}}
.next-section {{
    padding: 20px 32px;
    background: #050505;
    border-top: 2px solid #1a1a1a;
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
}}
.hidden {{ display: none; }}
.connection-lost {{
    position: fixed;
    top: 0; left: 0; right: 0;
    background: #a03030;
    color: white;
    text-align: center;
    padding: 6px;
    font-size: 12px;
    font-weight: bold;
    z-index: 999;
}}
</style>
</head>
<body>
<div id="conn-banner" class="connection-lost hidden">CONNECTION LOST — RECONNECTING...</div>

<div class="header">
    <span class="title">{title.upper()}</span>
    <span class="tc" id="timecode">--:--:--:--</span>
    <span class="clock" id="clock"></span>
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
let ws;
let reconnectTimer;

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

    if (OPERATOR_FILTER) {{
        const comment = comments[OPERATOR_FILTER] || '';
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

    if (OPERATOR_FILTER) {{
        const comment = comments[OPERATOR_FILTER] || '';
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

setInterval(updateClock, 1000);
updateClock();
connect();
</script>
</body>
</html>"""
