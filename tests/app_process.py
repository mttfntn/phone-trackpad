"""Starts the real helper (main.py) as a separate process for end-to-end tests.

It always runs with a throwaway home folder, so the real pairing file is never read or
written, and normally with --dry-run, so the mouse and keyboard are never touched.
"""
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

from helpers import APP_DIR


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AppProcess:
    def __init__(self, *args, home=None, python=sys.executable, cwd=None, main=None):
        self._tmp = None
        if home is None:
            self._tmp = tempfile.TemporaryDirectory()
            home = self._tmp.name
        self.home = home
        env = dict(os.environ, HOME=home, USERPROFILE=home, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [python, main or str(APP_DIR / "main.py"), *args], cwd=cwd or str(APP_DIR), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace")
        self.lines = []
        self._q = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            self.lines.append(line)
            self._q.put(line)
        self._q.put(None)

    def wait_for(self, pattern, timeout=60):
        """Returns the regex match of the first new output line matching `pattern`."""
        deadline = time.monotonic() + timeout
        rx = re.compile(pattern)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no line matching {pattern!r}; output so far:\n" + "\n".join(self.lines))
            try:
                line = self._q.get(timeout=left)
            except queue.Empty:
                continue
            if line is None:
                raise EOFError(f"process ended before {pattern!r}; output:\n" + "\n".join(self.lines))
            m = rx.search(line)
            if m:
                return m

    def wait_ready(self, timeout=60):
        """Waits for startup; returns (port, pin)."""
        port = int(self.wait_for(r"running as .* on port (\d+)", timeout).group(1))
        pin = self.wait_for(r"Pairing PIN: (\d{4})", timeout).group(1)
        # The link is printed a few milliseconds before the server listens: wait for it.
        deadline = time.monotonic() + 10
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                return port, pin
            except OSError:
                if time.monotonic() > deadline or self.proc.poll() is not None:
                    raise
                time.sleep(0.02)

    def finish(self, timeout=30):
        """Waits for the process to end by itself; returns its exit code."""
        code = self.proc.wait(timeout)
        time.sleep(0.1)
        return code

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        if self._tmp:
            try:
                self._tmp.cleanup()
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
