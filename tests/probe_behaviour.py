"""Records what the app does for a broad, fixed set of inputs, to compare two versions.

    python tests/probe_behaviour.py out.json                  # this checkout
    python tests/probe_behaviour.py out.json --app-root DIR   # another copy (e.g. a git worktree)
    python tests/compare_probes.py old.json new.json

Recorded:
  - input_backend with fake pynput, as Windows and as macOS: the exact mouse/keyboard events
    for a long list of phone messages;
  - the helper process (--dry-run, throwaway home): replies to every kind of message, the
    dry-run log, HTTP status for many paths, --simulate-focus toggling;
  - the phone page (node tests/web/probe.mjs): every message it sends for scripted gestures.
Anything that differs between runs of the same code (PIN, token, port, timing) is replaced
by a placeholder.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

MESSAGES = [
    {"t": "move", "dx": 0.3, "dy": 0.3}, {"t": "move", "dx": 0.8, "dy": -0.4}, {"t": "move", "dx": 25.5, "dy": -7.25},
    {"t": "move", "dx": -3, "dy": 0}, {"t": "move"}, {"t": "move", "dx": "x"},
    {"t": "click"}, {"t": "click", "button": "right", "count": 1}, {"t": "click", "button": "middle", "count": 2},
    {"t": "click", "button": "left", "count": 5}, {"t": "click", "button": "nope", "count": 0},
    {"t": "click", "count": "x"},
    {"t": "down", "button": "left"}, {"t": "up", "button": "left"}, {"t": "down"}, {"t": "up", "button": "right"},
    {"t": "scroll", "dx": 0, "dy": 0.25}, {"t": "scroll", "dx": 0.05, "dy": 0.05}, {"t": "scroll", "dx": -1.5, "dy": 2},
    {"t": "scroll", "dx": None},
    {"t": "zoom", "steps": 0.4}, {"t": "zoom", "steps": 0.7}, {"t": "zoom", "steps": -2.6}, {"t": "zoom", "steps": 99},
    {"t": "zoom", "steps": "z"},
    {"t": "text", "s": "Hello"}, {"t": "text", "s": "a\nb\n"}, {"t": "text", "s": "àèé ✓ 你好"}, {"t": "text", "s": ""},
    {"t": "text", "s": 42},
    *[{"t": "key", "name": k, "mods": []} for k in
      ["backspace", "enter", "tab", "esc", "delete", "space", "up", "down", "left", "right", "home", "end",
       "pageup", "pagedown", "f1", "f12", "a", "Z", "1", "=", "-", "/"]],
    {"t": "key", "name": "c", "mods": ["cmd"]}, {"t": "key", "name": "v", "mods": ["ctrl", "shift"]},
    {"t": "key", "name": "tab", "mods": ["alt"]}, {"t": "key", "name": "x", "mods": ["hyper", "cmd"]},
    {"t": "key", "name": "enter", "mods": None}, {"t": "key", "name": "nosuchkey", "mods": []},
    {"t": "key", "name": "", "mods": []},
    {"t": "volume", "level": 30}, {"t": "volume", "level": 250}, {"t": "volume", "level": -5},
    {"t": "volume", "level": 12.7}, {"t": "volume", "level": "x"},
    {"t": "mute", "on": True}, {"t": "mute", "on": False}, {"t": "mute"},
    {"t": "unknown"}, {"x": 1},
]

HTTP_PATHS = ["/", "/index.html", "/app.js", "/style.css", "/manifest.webmanifest", "/icon.svg", "/?x=1",
              "/main.py", "/../main.py", "/web/app.js", "/ws", "/favicon.ico", "/INDEX.HTML"]


def normalize(text, pin=None, token=None, port=None):
    if pin:
        text = text.replace(pin, "<PIN>")
    if token:
        text = text.replace(token, "<TOKEN>")
    if port:
        text = text.replace(str(port), "<PORT>")
    text = re.sub(r"\d+\.\d+\.\d+\.\d+", "<IP>", text)
    return text


def probe_backend(app_root):
    """Exact pynput calls for MESSAGES, through the server's dispatch, on both platforms."""
    os.environ["APP_ROOT"] = str(app_root)
    sys.path.insert(0, str(HERE))
    from helpers import input_backend_module  # noqa: E402  (after APP_ROOT is set)
    import server as server_mod
    results = {}
    for platform in ("win32", "darwin"):
        with input_backend_module(platform) as mod:
            # Deterministic clock for macOS double-click detection.
            # (Only the module's own reference is replaced; the real time module stays untouched.)
            ticks = iter(i * 0.1 for i in range(100000))
            mod.time = types.SimpleNamespace(monotonic=lambda: next(ticks))
            b = mod.InputBackend()
            cls = getattr(server_mod, "TrackpadServer", None) or server_mod.PhonePadServer
            srv = cls(b, pairing=None, name="x", volume=None)
            log = []
            for msg in MESSAGES:
                b.mouse.log.clear()
                b.keyboard.log.clear()
                mod._fake_quartz.posted.clear()
                out = []
                import builtins
                real_print = builtins.print
                builtins.print = lambda *a, **k: out.append(" ".join(map(str, a)))
                try:
                    srv._dispatch(msg.get("t"), msg)
                except Exception as e:  # recorded, not fatal
                    out.append(f"EXCEPTION {type(e).__name__}: {e}")
                finally:
                    builtins.print = real_print
                log.append({"msg": msg, "mouse": [repr(e) for e in b.mouse.log],
                            "keyboard": [repr(e) for e in b.keyboard.log],
                            "quartz": [repr(e) for e in mod._fake_quartz.posted], "printed": out})
            results[platform] = log
    return results


async def probe_process(app_root):
    sys.path.insert(0, str(HERE))
    from app_process import AppProcess, free_port
    from websockets.asyncio.client import connect

    out = {}
    port = free_port()
    with AppProcess("--dry-run", "--no-focus", "--port", str(port), "--name", "Probe PC") as app:
        port, pin = app.wait_ready()

        http = {}
        for path in HTTP_PATHS:
            def get(path=path):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
                        return [r.status, r.headers.get("Content-Type"), r.headers.get("Cache-Control"),
                                hashlib.sha256(r.read()).hexdigest()[:16]]
                except urllib.error.HTTPError as e:
                    return [e.code, e.headers.get("Content-Type"), None, e.read().decode()]
            http[path] = await asyncio.to_thread(get)
        out["http"] = http

        replies = []

        class Reader:
            """Reads messages in the background, so waiting with a timeout never cancels a recv()."""
            def __init__(self, ws):
                self.q = asyncio.Queue()
                self.task = asyncio.ensure_future(self._run(ws))

            async def _run(self, ws):
                async for raw in ws:
                    await self.q.put(json.loads(raw))

            async def all(self, wait=0.3):
                got = []
                while True:
                    try:
                        got.append(await asyncio.wait_for(self.q.get(), wait))
                    except asyncio.TimeoutError:
                        return got

        async with connect(f"ws://127.0.0.1:{port}/ws") as ws:
            r = Reader(ws)
            await ws.send(json.dumps({"t": "move", "dx": 1, "dy": 1}))
            replies.append(["move before auth", await r.all()])
            await ws.send(json.dumps({"t": "hello", "token": "wrong"}))
            replies.append(["bad token", await r.all()])
            await ws.send(json.dumps({"t": "pair", "pin": "abcd"}))
            replies.append(["bad pin", await r.all()])
            await ws.send(json.dumps({"t": "pair", "pin": pin, "device": "Probe phone"}))
            first = await r.all()
            token = first[0].get("token", "")
            replies.append(["pair", first])
            for msg in MESSAGES:
                await ws.send(json.dumps(msg))
                await asyncio.sleep(0.03)
            await ws.send('{"t":"ping"}')
            replies.append(["after messages", await r.all(0.8)])
            for raw in ("junk", "[]", "7"):
                await ws.send(raw)
            await ws.send('{"t":"ping"}')
            replies.append(["junk then ping", await r.all()])
            r.task.cancel()
        async with connect(f"ws://127.0.0.1:{port}/ws") as ws2:
            r2 = Reader(ws2)
            await ws2.send(json.dumps({"t": "hello", "token": token}))
            replies.append(["hello with token", await r2.all()])
            r2.task.cancel()
        await asyncio.sleep(0.3)
        lines = list(app.lines)
    norm = lambda s: normalize(s, pin, token, port)  # noqa: E731
    out["replies"] = json.loads(norm(json.dumps(replies)))
    # Startup banner and QR code differ only by name/IP/PIN; keep the log lines after them.
    log = [norm(l) for l in lines if l.startswith("[dry-run]") or "Ignored" in l or "Paired" in l
           or "connected" in l or "disconnected" in l]
    out["log"] = log

    port = free_port()
    with AppProcess("--dry-run", "--simulate-focus", "--port", str(port)) as app:
        port, pin = app.wait_ready()
        async with connect(f"ws://127.0.0.1:{port}/ws") as ws:
            await ws.send(json.dumps({"t": "pair", "pin": pin}))
            r = Reader(ws)
            for _ in range(3):
                await ws.send(json.dumps({"t": "click"}))
            got = [m for m in await r.all(0.5) if m["t"] in ("focus", "hover")]
            r.task.cancel()
        out["simulate_focus"] = got
    return out


def probe_page(app_root):
    node = shutil.which("node")
    if not node:
        return "node not found"
    env = dict(os.environ, APP_ROOT=str(app_root))
    proc = subprocess.run([node, str(HERE / "web" / "probe.mjs")], capture_output=True, text=True,
                          encoding="utf-8", env=env, check=True)
    return json.loads(proc.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--app-root", default=str(HERE.parent / "desktop"))
    args = ap.parse_args()
    root = Path(args.app_root).resolve()
    os.environ["APP_ROOT"] = str(root)
    result = {
        "backend": probe_backend(root),
        "process": asyncio.run(probe_process(root)),
        "page": probe_page(root),
    }
    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
