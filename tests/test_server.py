"""server: the HTTP page, the WebSocket protocol, authentication and message dispatch.

A real server runs on 127.0.0.1 with a recording backend instead of real input.
"""
import asyncio
import json
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts the app folder on sys.path)
import pairing
import server as server_mod
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

SERVER_CLASS = getattr(server_mod, "TrackpadServer", None) or getattr(server_mod, "PhonePadServer")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RecordingBackend:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def record(*args):
            if name == "key" and args and args[0] == "notakey":
                raise ValueError("unknown key")
            self.calls.append((name, *args))
        return record


class FakeVolume:
    def __init__(self):
        self.level, self.muted = 30, False
        self.sets = []

    async def get(self):
        return self.level, self.muted

    async def set_level(self, level):
        self.level = level
        self.sets.append(("level", level))

    async def set_muted(self, muted):
        self.muted = muted
        self.sets.append(("muted", muted))


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        for name, value in (("CONFIG_DIR", d), ("CONFIG_FILE", d / "config.json"),
                            ("OLD_CONFIG_FILE", d / "old" / "config.json")):
            p = mock.patch.object(pairing, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)
        quiet = mock.patch("builtins.print")
        self.printed = quiet.start()
        self.addCleanup(quiet.stop)

        self.backend = RecordingBackend()
        self.volume = FakeVolume()
        self.pairing = pairing.Pairing()
        self.srv = SERVER_CLASS(self.backend, self.pairing, "Test PC", self.volume)
        self.port = free_port()
        self.task = asyncio.ensure_future(self.srv.run(host="127.0.0.1", port=self.port))
        self.poll = asyncio.ensure_future(self.srv.poll_volume(interval=0.05))
        for _ in range(100):
            try:
                _, w = await asyncio.open_connection("127.0.0.1", self.port)
                w.close()
                break
            except OSError:
                await asyncio.sleep(0.02)

    async def asyncTearDown(self):
        for t in (self.task, self.poll):
            t.cancel()
        await asyncio.gather(self.task, self.poll, return_exceptions=True)

    # ---------- helpers ----------
    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    async def http(self, path):
        def get():
            try:
                with urllib.request.urlopen(self.url(path), timeout=5) as r:
                    return r.status, r.headers.get("Content-Type"), r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.headers.get("Content-Type"), e.read()
        return await asyncio.to_thread(get)

    async def ws(self):
        c = await connect(f"ws://127.0.0.1:{self.port}/ws")
        self.addAsyncCleanup(c.close)
        return c

    @staticmethod
    async def recv(c, timeout=2):
        return json.loads(await asyncio.wait_for(c.recv(), timeout))

    async def recv_until(self, c, t, timeout=2):
        while True:
            msg = await self.recv(c, timeout)
            if msg.get("t") == t:
                return msg

    async def paired(self):
        c = await self.ws()
        await c.send(json.dumps({"t": "pair", "pin": self.pairing.pin, "device": "Phone"}))
        first = await self.recv(c)
        self.assertEqual(first["t"], "paired")
        return c, first

    async def settle(self):
        await asyncio.sleep(0.15)

    # ---------- HTTP ----------
    async def test_serves_page_files(self):
        for path, ctype in (("/", "text/html"), ("/index.html", "text/html"), ("/app.js", "text/javascript"),
                            ("/style.css", "text/css"), ("/manifest.webmanifest", "application/manifest+json"),
                            ("/icon.svg", "image/svg+xml"), ("/?pin=1", "text/html")):
            status, got, body = await self.http(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(got.startswith(ctype), (path, got))
            self.assertTrue(body)

    async def test_page_is_the_file_on_disk(self):
        _, _, body = await self.http("/app.js")
        self.assertEqual(body, (server_mod.WEB_DIR / "app.js").read_bytes())

    async def test_other_paths_are_404(self):
        for path in ("/server.py", "/../server.py", "/web/app.js", "/%2e%2e/main.py", "/ws", "/APP.JS"):
            status, _, _ = await self.http(path)
            self.assertEqual(status, 404, path)

    async def test_websocket_only_on_ws_path(self):
        with self.assertRaises(InvalidStatus):
            await connect(f"ws://127.0.0.1:{self.port}/")

    # ---------- authentication ----------
    async def test_pair_with_right_pin(self):
        c, first = await self.paired()
        self.assertEqual(first["name"], "Test PC")
        self.assertIn(first["os"], ("mac", "windows"))
        self.assertTrue(self.pairing.check(first["token"]))
        self.assertEqual(await self.recv(c), {"t": "focus", "editable": False})
        self.assertEqual(await self.recv(c), {"t": "hover", "editable": False})

    async def test_pair_with_wrong_pin(self):
        c = await self.ws()
        wrong = "0000" if self.pairing.pin != "0000" else "1111"
        await c.send(json.dumps({"t": "pair", "pin": wrong}))
        self.assertEqual(await self.recv(c), {"t": "error", "msg": "bad_pin"})
        await c.send(json.dumps({"t": "move", "dx": 5, "dy": 5}))
        self.assertEqual(await self.recv(c), {"t": "error", "msg": "not_authenticated"})
        self.assertEqual(self.backend.calls, [])

    async def test_non_ascii_pin_is_a_wrong_pin(self):
        c = await self.ws()
        await c.send(json.dumps({"t": "pair", "pin": "é"}))
        self.assertEqual(await self.recv(c), {"t": "error", "msg": "bad_pin"})
        await c.send('{"t":"ping"}')
        self.assertEqual(await self.recv(c), {"t": "pong"}, "connection still open")

    async def test_pairing_locks_after_ten_wrong_pins(self):
        c, first = await self.paired()
        c2 = await self.ws()
        wrong = "0000" if self.pairing.pin != "0000" else "1111"
        replies = []
        for _ in range(12):
            await c2.send(json.dumps({"t": "pair", "pin": wrong}))
            replies.append((await self.recv(c2))["msg"])
        self.assertEqual(replies, ["bad_pin"] * 9 + ["pairing_locked"] * 3)
        await c2.send(json.dumps({"t": "pair", "pin": self.pairing.pin}))
        self.assertEqual(await self.recv(c2), {"t": "error", "msg": "pairing_locked"})
        # The phone paired before still connects with its token.
        c3 = await self.ws()
        await c3.send(json.dumps({"t": "hello", "token": first["token"]}))
        self.assertEqual((await self.recv(c3))["t"], "paired")

    async def test_hello_with_token(self):
        _, first = await self.paired()
        c = await self.ws()
        await c.send(json.dumps({"t": "hello", "token": first["token"]}))
        msg = await self.recv(c)
        self.assertEqual(msg["t"], "paired")
        self.assertEqual(msg["token"], first["token"])

    async def test_hello_with_bad_token(self):
        c = await self.ws()
        for token in ("nope", None, 5):
            await c.send(json.dumps({"t": "hello", "token": token}))
            self.assertEqual(await self.recv(c), {"t": "error", "msg": "bad_token"})

    async def test_unauthenticated_input_refused(self):
        c = await self.ws()
        for t in ("move", "click", "text", "key", "volume", "mute", "scroll", "zoom", "down", "up"):
            await c.send(json.dumps({"t": t}))
            self.assertEqual(await self.recv(c), {"t": "error", "msg": "not_authenticated"})
        await self.settle()
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.volume.sets, [])

    async def test_ping_works_without_auth(self):
        c = await self.ws()
        await c.send('{"t":"ping"}')
        self.assertEqual(await self.recv(c), {"t": "pong"})

    async def test_junk_is_ignored(self):
        c = await self.ws()
        for raw in ("not json", "[1,2]", "42", '"s"', "null"):
            await c.send(raw)
        await c.send('{"t":"ping"}')
        self.assertEqual(await self.recv(c), {"t": "pong"})

    async def test_oversized_message_closes_connection(self):
        c = await self.ws()
        await c.send("x" * (65 * 1024))
        with self.assertRaises(Exception):
            await self.recv(c)

    # ---------- dispatch ----------
    async def test_dispatch_to_backend(self):
        c, _ = await self.paired()
        msgs = [
            {"t": "move", "dx": 1.5, "dy": -2},
            {"t": "move"},
            {"t": "click", "button": "right", "count": 2},
            {"t": "click"},
            {"t": "zoom", "steps": 100},
            {"t": "zoom", "steps": -100},
            {"t": "zoom", "steps": 0.5},
            {"t": "down", "button": "left"},
            {"t": "up"},
            {"t": "scroll", "dx": 0.1, "dy": -0.2},
            {"t": "text", "s": "héllo ✓"},
            {"t": "text", "s": 123},
            {"t": "key", "name": "a", "mods": ["cmd"]},
            {"t": "key", "name": "enter", "mods": None},
            {"t": "unknown"},
        ]
        for m in msgs:
            await c.send(json.dumps(m))
        await self.settle()
        self.assertEqual(self.backend.calls, [
            ("move", 1.5, -2.0), ("move", 0.0, 0.0),
            ("click", "right", 2), ("click", "left", 1),
            ("zoom", 20.0), ("zoom", -20.0), ("zoom", 0.5),
            ("down", "left"), ("up", "left"),
            ("scroll", 0.1, -0.2),
            ("type_text", "héllo ✓"), ("type_text", "123"),
            ("key", "a", ["cmd"]), ("key", "enter", []),
        ])

    async def test_bad_values_are_ignored_not_fatal(self):
        c, _ = await self.paired()
        for m in ({"t": "move", "dx": "x"}, {"t": "zoom", "steps": "big"}, {"t": "key", "name": "notakey"},
                  {"t": "volume", "level": "loud"}, {"t": "scroll", "dx": None}):
            await c.send(json.dumps(m))
        await c.send(json.dumps({"t": "move", "dx": 1, "dy": 1}))
        await self.settle()
        self.assertEqual(self.backend.calls, [("move", 1.0, 1.0)])

    async def test_volume_and_mute(self):
        c, _ = await self.paired()
        vol = await self.recv_until(c, "volume")
        self.assertEqual(vol, {"t": "volume", "level": 30, "muted": False})
        for m in ({"t": "volume", "level": 150}, {"t": "volume", "level": -3}, {"t": "volume", "level": 42.9},
                  {"t": "mute", "on": True}, {"t": "mute", "on": 0}):
            await c.send(json.dumps(m))
            await asyncio.sleep(0.02)
        await self.settle()
        self.assertEqual(self.volume.sets, [("level", 100), ("level", 0), ("level", 42),
                                            ("muted", True), ("muted", False)])

    async def test_volume_change_on_computer_reaches_phone(self):
        c, _ = await self.paired()
        await self.recv_until(c, "volume")
        self.volume.level, self.volume.muted = 77, True
        self.assertEqual(await self.recv_until(c, "volume"), {"t": "volume", "level": 77, "muted": True})

    async def test_volume_set_from_phone_is_not_echoed(self):
        c, _ = await self.paired()
        await self.recv_until(c, "volume")
        await c.send(json.dumps({"t": "volume", "level": 55}))
        await asyncio.sleep(0.3)
        await c.send('{"t":"ping"}')
        # The next message is the pong: no "volume" echo of the phone's own change.
        self.assertEqual(await self.recv(c), {"t": "pong"})

    async def test_focus_and_hover_broadcast(self):
        c1, _ = await self.paired()
        c2, _ = await self.paired()
        for c in (c1, c2):
            await self.recv_until(c, "hover")
        self.srv.set_focus(True)
        self.srv.set_hover(True)
        for c in (c1, c2):
            self.assertEqual(await self.recv_until(c, "focus"), {"t": "focus", "editable": True})
            self.assertEqual(await self.recv_until(c, "hover"), {"t": "hover", "editable": True})
        # A phone connecting later gets the current state right away.
        c3, _ = await self.paired()
        self.assertEqual(await self.recv(c3), {"t": "focus", "editable": True})

    async def test_disconnect_removes_client(self):
        c, _ = await self.paired()
        self.assertEqual(len(self.srv.clients), 1)
        await c.close()
        await self.settle()
        self.assertEqual(len(self.srv.clients), 0)
        self.srv.set_focus(True)  # must not fail with nobody connected


class VolumeReadingTest(unittest.IsolatedAsyncioTestCase):
    """The volume is read once at start, then only while a phone is connected."""

    async def test_reads_only_with_a_phone(self):
        reads = []

        class CountingVolume(FakeVolume):
            async def get(self):
                reads.append(len(srv.clients))
                return await super().get()

        srv = SERVER_CLASS(RecordingBackend(), None, "x", CountingVolume())
        task = asyncio.ensure_future(srv.poll_volume(interval=0.02))
        try:
            await asyncio.sleep(0.3)
            self.assertEqual(reads, [0], "one reading at start, none while nobody is connected")
            phone = mock.AsyncMock()
            await srv._on_auth(phone, "tok")
            await asyncio.sleep(0.01)
            self.assertEqual(reads[1], 1, "a connecting phone triggers a reading right away")
            await asyncio.sleep(0.3)
            self.assertGreater(len(reads), 5, "then every interval")
            srv.clients.clear()
            await asyncio.sleep(0.1)
            count = len(reads)
            await asyncio.sleep(0.3)
            self.assertEqual(len(reads), count, "stops again when the phone leaves")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_unreadable_volume_is_skipped(self):
        class Broken(FakeVolume):
            async def get(self):
                raise OSError("no audio device")

        srv = SERVER_CLASS(RecordingBackend(), None, "x", Broken())
        task = asyncio.ensure_future(srv.poll_volume(interval=0.01))
        await asyncio.sleep(0.05)
        self.assertFalse(task.done())
        self.assertIsNone(srv.volume_state)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class NoVolumeTest(ServerTest):
    """Same server without volume control (e.g. no audio device library): volume messages do nothing."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.srv.volume = None

    async def test_volume_and_mute(self):
        c, _ = await self.paired()
        await c.send(json.dumps({"t": "volume", "level": 50}))
        await c.send(json.dumps({"t": "mute", "on": True}))
        await self.settle()
        self.assertEqual(self.volume.sets, [])

    async def test_volume_change_on_computer_reaches_phone(self):
        pass  # not applicable

    async def test_volume_set_from_phone_is_not_echoed(self):
        pass  # not applicable


if __name__ == "__main__":
    unittest.main()
