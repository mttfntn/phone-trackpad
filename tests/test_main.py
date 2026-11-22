"""main: command-line options, port handling and the whole helper end to end (as a separate
process with --dry-run and a throwaway home folder)."""
import asyncio
import http.server
import json
import socket
import sys
import threading
import unittest
import urllib.request

from app_process import AppProcess, free_port
from helpers import fresh_import
from websockets.asyncio.client import connect


class Checks(unittest.TestCase):
    def test_unsupported_system_refused_unless_dry_run(self):
        import io
        from unittest import mock
        main = fresh_import("main")
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(sys, "argv", ["main.py"]), \
                self.assertRaises(SystemExit) as stop:
            main.main()
        self.assertIn("Windows and macOS only", str(stop.exception.code))
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(sys, "argv", ["main.py", "--dry-run", "--port", "x"]), \
                mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as stop:
            main.main()
        self.assertEqual(stop.exception.code, 2, "--dry-run gets past the system check (then --port x fails)")

    def test_old_python_refused(self):
        from unittest import mock
        import version
        with mock.patch.object(sys, "version_info", (3, 9, 6)), mock.patch.object(sys, "version", "3.9.6 (fake)"), \
                self.assertRaises(SystemExit) as stop:
            fresh_import("main")
        self.assertIn(f"needs Python {version.MIN_PYTHON[0]}.{version.MIN_PYTHON[1]} or newer", str(stop.exception.code))
        self.assertIn("this is Python 3.9.6", str(stop.exception.code))
        fresh_import("main")

    def test_bonjour_stop_is_safe_when_start_never_finished(self):
        disc = fresh_import("discovery")

        async def run():
            a = disc.Advertiser("Test", free_port(), "mac")
            await a.stop()                      # never started
            task = asyncio.ensure_future(a.start())
            await asyncio.sleep(0)
            task.cancel()                       # cancelled during mDNS probing
            await asyncio.gather(task, return_exceptions=True)
            await a.stop()
            await a.stop()                      # twice is fine
        asyncio.run(run())


class PortHelpers(unittest.TestCase):
    def setUp(self):
        self.main = fresh_import("main")

    def test_port_free(self):
        port = free_port()
        self.assertTrue(self.main.port_free(port))
        with socket.socket() as s:
            s.bind(("0.0.0.0", port))
            s.listen()
            self.assertFalse(self.main.port_free(port))

    def test_next_free_port_skips_busy(self):
        if not hasattr(self.main, "next_free_port"):
            self.skipTest("no automatic port choice in this version")
        base = free_port()
        with socket.socket() as s:
            try:
                s.bind(("0.0.0.0", base + 1))
            except OSError:
                self.skipTest("neighbour port busy")
            s.listen()
            got = self.main.next_free_port(base)
        self.assertGreater(got, base + 1)


def http_get(port, path="/"):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return r.status, r.read()


async def session(port, pin, messages, settle=0.6):
    """Pairs, sends `messages`, and returns every message the helper sent back."""
    got = []
    async with connect(f"ws://127.0.0.1:{port}/ws") as ws:
        await ws.send(json.dumps({"t": "pair", "pin": pin, "device": "test"}))
        got.append(json.loads(await asyncio.wait_for(ws.recv(), 10)))
        for m in messages:
            await ws.send(json.dumps(m))
        await asyncio.sleep(settle)
        while True:
            try:
                got.append(json.loads(await asyncio.wait_for(ws.recv(), 0.2)))
            except asyncio.TimeoutError:
                break
    return got


class EndToEnd(unittest.TestCase):
    def test_dry_run_full_session(self):
        port = free_port()
        with AppProcess("--dry-run", "--no-focus", "--port", str(port), "--name", "E2E PC") as app:
            got_port, pin = app.wait_ready()
            self.assertEqual(got_port, port)
            self.assertTrue(any(f"http://" in l and f":{port}/#pin={pin}" in l for l in app.lines))
            status, body = http_get(port)
            self.assertEqual(status, 200)
            self.assertIn(b"<title>", body)
            replies = asyncio.run(session(port, pin, [
                {"t": "move", "dx": 3, "dy": 4}, {"t": "click", "button": "left", "count": 1},
                {"t": "text", "s": "hi"}, {"t": "key", "name": "a", "mods": ["cmd"]},
                {"t": "volume", "level": 20}, {"t": "mute", "on": True},
            ]))
            app.wait_for(r"\[dry-run\] mute True", 10)
        self.assertEqual(replies[0]["t"], "paired")
        self.assertEqual(replies[0]["name"], "E2E PC")
        out = "\n".join(app.lines)
        for expected in ("[dry-run] move(3.0, 4.0)", "[dry-run] click('left', 1)", "[dry-run] type_text('hi',)",
                         "[dry-run] key('a', ['cmd'])", "[dry-run] volume 20", "[dry-run] mute True"):
            self.assertIn(expected, out)
        self.assertIn({"t": "volume", "level": 50, "muted": False}, replies)

    def test_simulate_focus(self):
        port = free_port()
        with AppProcess("--dry-run", "--simulate-focus", "--port", str(port)) as app:
            _, pin = app.wait_ready()
            replies = asyncio.run(session(port, pin, [{"t": "click"}, {"t": "click"}]))
        states = [(m["t"], m["editable"]) for m in replies if m["t"] in ("focus", "hover")]
        # Connect: focus off, hover on. Each click toggles a fake text-field focus.
        self.assertEqual(states, [("focus", False), ("hover", True), ("focus", True), ("hover", False),
                                  ("focus", False), ("hover", True)])

    def test_simulate_focus_needs_dry_run(self):
        with AppProcess("--simulate-focus") as app:
            self.assertEqual(app.finish(), 2)
        self.assertIn("--simulate-focus needs --dry-run", "\n".join(app.lines))

    def test_second_copy_on_same_port_stops(self):
        port = free_port()
        with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as first:
            first.wait_ready()
            with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as second:
                self.assertEqual(second.finish(), 1)
        self.assertIn("already running", "\n".join(second.lines))

    def test_port_held_by_other_program_moves_on(self):
        port = free_port()

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"some other program")

        other = http.server.ThreadingHTTPServer(("0.0.0.0", port), Quiet)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        try:
            with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as app:
                got, _ = app.wait_ready()
                self.assertNotEqual(got, port)
                self.assertEqual(http_get(got)[0], 200)
            self.assertIn("used by another program", "\n".join(app.lines))
        finally:
            other.shutdown()
            other.server_close()

    def test_paired_phone_survives_restart(self):
        port = free_port()
        with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as app:
            _, pin = app.wait_ready()
            token = asyncio.run(session(port, pin, []))[0]["token"]
            home = app.home
            app._tmp, keep = None, app._tmp  # keep the home folder for the second run
        try:
            with AppProcess("--dry-run", "--no-focus", "--port", str(port), home=home) as again:
                port2, _ = again.wait_ready()

                async def hello():
                    async with connect(f"ws://127.0.0.1:{port2}/ws") as ws:
                        await ws.send(json.dumps({"t": "hello", "token": token}))
                        return json.loads(await asyncio.wait_for(ws.recv(), 10))
                self.assertEqual(asyncio.run(hello())["t"], "paired")
        finally:
            keep.cleanup()

    def test_restart_after_a_phone_disconnects_keeps_the_port(self):
        port = free_port()
        with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as app:
            _, pin = app.wait_ready()
            asyncio.run(session(port, pin, [{"t": "move", "dx": 1, "dy": 1}]))
        with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as again:
            got, _ = again.wait_ready()
        self.assertEqual(got, port, "\n".join(again.lines[:3]))

    def test_link_printed_before_bonjour_finishes(self):
        import time
        port = free_port()
        start = time.monotonic()
        with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as app:
            app.wait_ready()
            elapsed = time.monotonic() - start
        # Bonjour registration alone takes about 1.2 s; the link used to wait for it.
        self.assertLess(elapsed, 1.0 if sys.platform == "darwin" else 5.0)

    def test_tools_test_client_runs(self):
        import subprocess
        from helpers import REPO
        port = free_port()
        with AppProcess("--dry-run", "--no-focus", "--port", str(port)) as app:
            _, pin = app.wait_ready()
            r = subprocess.run([sys.executable, str(REPO / "tools" / "test_client.py"), pin, "--port", str(port)],
                               capture_output=True, text=True, timeout=60)
            app.wait_for(r"\[dry-run\] scroll", 10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("'t': 'paired'", r.stdout)

    @unittest.skipUnless(sys.platform in ("darwin", "win32"), "focus watcher exists on macOS and Windows only")
    def test_starts_with_focus_watcher(self):
        port = free_port()
        with AppProcess("--dry-run", "--port", str(port)) as app:
            app.wait_ready()
            self.assertEqual(http_get(port)[0], 200)
        self.assertNotIn("Traceback", "\n".join(app.lines))


if __name__ == "__main__":
    unittest.main()
