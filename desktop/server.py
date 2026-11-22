"""Serves the phone web page and a WebSocket that authenticates phones and turns their messages into input."""
import asyncio
import json
import socket
import sys
from http import HTTPStatus
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

OS_NAME = "mac" if sys.platform == "darwin" else "windows"

WEB_DIR = Path(__file__).parent / "web"
WS_PATH = "/ws"
# Only these files are ever served, so nothing else on disk is reachable over HTTP.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}


def _http_response(status, body, content_type):
    headers = Headers([
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-cache"),
        ("Connection", "close"),
    ])
    return Response(status.value, status.phrase, headers, body)


def serve_static(connection, request):
    """websockets process_request hook: answers plain HTTP GETs, lets WebSocket upgrades through."""
    path = request.path.split("?", 1)[0]
    if path == WS_PATH and "upgrade" in request.headers.get("Connection", "").lower():
        return None
    entry = STATIC_FILES.get(path)
    if entry is None:
        return _http_response(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")
    filename, content_type = entry
    return _http_response(HTTPStatus.OK, (WEB_DIR / filename).read_bytes(), content_type)


class TrackpadServer:
    def __init__(self, backend, pairing, name=None, volume=None):
        self.backend = backend
        self.pairing = pairing
        self.name = name or socket.gethostname()
        self.volume = volume
        self.clients = set()
        self.editable = False
        self.hover_editable = False
        self.volume_state = None  # (level, muted) last sent to phones

    async def run(self, host="0.0.0.0", port=8765):
        async with serve(self._handle, host, port, process_request=serve_static,
                         max_size=64 * 1024, ping_interval=20) as server:
            await server.serve_forever()

    def _broadcast(self, msg):
        msg = json.dumps(msg)
        for ws in list(self.clients):
            asyncio.ensure_future(self._safe_send(ws, msg))

    def set_focus(self, editable):
        """Called on the event loop whenever the focused element changes editability."""
        self.editable = editable
        self._broadcast({"t": "focus", "editable": editable})

    def set_hover(self, editable):
        """Called on the event loop whenever the element under the cursor changes editability."""
        self.hover_editable = editable
        self._broadcast({"t": "hover", "editable": editable})

    def _volume_msg(self):
        level, muted = self.volume_state
        return {"t": "volume", "level": level, "muted": muted}

    async def poll_volume(self, interval=1.0):
        """Keeps phones in sync with volume changes made on the computer itself."""
        while self.volume:
            try:
                state = await self.volume.get()
            except Exception:  # e.g. no audio device right now
                state = None
            if state and state != self.volume_state:
                self.volume_state = state
                self._broadcast(self._volume_msg())
            await asyncio.sleep(interval)

    async def _set_volume(self, level=None, muted=None):
        try:
            if level is not None:
                await self.volume.set_level(level)
            if muted is not None:
                await self.volume.set_muted(muted)
        except Exception as e:
            print(f"Volume change failed: {e}")
            return
        # Remember what was set so the poller doesn't echo it back mid-drag.
        old_level, old_muted = self.volume_state or (0, False)
        self.volume_state = (old_level if level is None else level, old_muted if muted is None else muted)

    @staticmethod
    async def _safe_send(ws, msg):
        try:
            await ws.send(msg)
        except ConnectionClosed:
            pass

    async def _handle(self, ws):
        peer = ws.remote_address[0] if ws.remote_address else "?"
        authed = False
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    t = msg.get("t")
                except (ValueError, AttributeError):
                    continue

                if t == "ping":
                    await ws.send('{"t":"pong"}')
                elif t == "pair":
                    token = self.pairing.pair(msg.get("pin", ""), msg.get("device", ""))
                    if token:
                        authed = True
                        print(f"Paired new device {msg.get('device', '?')!r} from {peer}")
                        await self._on_auth(ws, token)
                    else:
                        await ws.send('{"t":"error","msg":"bad_pin"}')
                elif t == "hello":
                    token = msg.get("token")
                    if self.pairing.check(token):
                        authed = True
                        print(f"{self.pairing.device_name(token)!r} connected from {peer}")
                        await self._on_auth(ws, token)
                    else:
                        await ws.send('{"t":"error","msg":"bad_token"}')
                elif not authed:
                    await ws.send('{"t":"error","msg":"not_authenticated"}')
                else:
                    self._dispatch(t, msg)
        except ConnectionClosed:
            pass
        finally:
            if ws in self.clients:
                self.clients.discard(ws)
                print(f"Device at {peer} disconnected")

    async def _on_auth(self, ws, token):
        self.clients.add(ws)
        await ws.send(json.dumps({"t": "paired", "token": token, "name": self.name, "os": OS_NAME}))
        await ws.send(json.dumps({"t": "focus", "editable": self.editable}))
        await ws.send(json.dumps({"t": "hover", "editable": self.hover_editable}))
        if self.volume_state:
            await ws.send(json.dumps(self._volume_msg()))

    def _dispatch(self, t, msg):
        b = self.backend
        try:
            if t == "move":
                b.move(float(msg.get("dx", 0)), float(msg.get("dy", 0)))
            elif t == "click":
                b.click(msg.get("button", "left"), msg.get("count", 1))
            elif t == "zoom":
                b.zoom(max(-20.0, min(20.0, float(msg.get("steps", 0)))))
            elif t == "down":
                b.down(msg.get("button", "left"))
            elif t == "up":
                b.up(msg.get("button", "left"))
            elif t == "scroll":
                b.scroll(float(msg.get("dx", 0)), float(msg.get("dy", 0)))
            elif t == "text":
                b.type_text(str(msg.get("s", "")))
            elif t == "key":
                b.key(msg.get("name", ""), msg.get("mods") or [])
            elif t == "volume" and self.volume:
                level = max(0, min(100, int(msg.get("level", 0))))
                asyncio.ensure_future(self._set_volume(level=level))
            elif t == "mute" and self.volume:
                asyncio.ensure_future(self._set_volume(muted=bool(msg.get("on"))))
        except (ValueError, TypeError) as e:
            print(f"Ignored bad {t!r} message: {e}")
