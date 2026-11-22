"""Checks a built release zip the way a user gets it: unzip, double-click the launcher, open the page.

    python tests/check_package.py dist/phone-trackpad-1.0.0.zip

1. The zip holds exactly the expected files (launchers, app, README, LICENSE), nothing from
   tests/, tools/ or a local .venv; the .command file is executable and the .bat file uses
   Windows line endings.
2. The launcher for this system (Phone Trackpad.command on macOS, Phone Trackpad.bat on
   Windows) runs from a fresh unzip: it creates the private environment, installs the
   requirements from PyPI and starts the helper (--dry-run, throwaway home folder, so no real
   input and no real pairing file), and the phone page answers.
Prints "PROBLEMS: none" on success; exits non-zero otherwise.
"""
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "Phone Trackpad/"
EXPECTED = {
    "Phone Trackpad.command", "Phone Trackpad.bat", "README.md", "LICENSE",
    "desktop/main.py", "desktop/server.py", "desktop/input_backend.py", "desktop/pairing.py",
    "desktop/volume.py", "desktop/discovery.py", "desktop/version.py", "desktop/requirements.txt",
    "desktop/focus/__init__.py", "desktop/focus/mac.py", "desktop/focus/windows.py",
    "desktop/web/index.html", "desktop/web/app.js", "desktop/web/style.css",
    "desktop/web/manifest.webmanifest", "desktop/web/icon.svg",
}


def check_contents(zip_path, problems):
    with zipfile.ZipFile(zip_path) as z:
        infos = {i.filename: i for i in z.infolist()}
        names = {n[len(TOP):] for n in infos if n.startswith(TOP)}
        if len(names) != len(infos):
            problems.append(f"entries outside {TOP!r}: {sorted(n for n in infos if not n.startswith(TOP))}")
        if names != EXPECTED:
            problems.append(f"missing {sorted(EXPECTED - names)}, unexpected {sorted(names - EXPECTED)}")
        cmd = infos.get(TOP + "Phone Trackpad.command")
        if cmd and not (cmd.external_attr >> 16) & stat.S_IXUSR:
            problems.append("Phone Trackpad.command is not executable")
        bat = z.read(TOP + "Phone Trackpad.bat") if TOP + "Phone Trackpad.bat" in infos else b""
        if bat.count(b"\n") != bat.count(b"\r\n"):
            problems.append("Phone Trackpad.bat does not use CRLF line endings")
        if b"GNU GENERAL PUBLIC LICENSE" not in z.read(TOP + "LICENSE"):
            problems.append("LICENSE is not the GPL text")
        ver = re.search(rb'VERSION = "([^"]+)"', z.read(TOP + "desktop/version.py")).group(1).decode()
        if not Path(zip_path).name == f"phone-trackpad-{ver}.zip":
            problems.append(f"zip name {Path(zip_path).name} does not match version {ver}")
    return ver


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_launcher(zip_path, version, problems, timeout=600):
    work = Path(tempfile.mkdtemp(prefix="phone-trackpad-check-"))
    home = work / "home"
    home.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(work)
        for info in z.infolist():  # extractall drops Unix permissions: put the exec bit back
            mode = info.external_attr >> 16
            if mode:
                os.chmod(work / info.filename, mode & 0o777)
    app = work / "Phone Trackpad"
    port = free_port()
    args = ["--dry-run", "--no-focus", "--port", str(port), "--name", "PackageCheck"]  # no space: keeps cmd /c quoting simple
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONUNBUFFERED="1")
    if os.name == "nt":
        cmd = ["cmd", "/c", str(app / "Phone Trackpad.bat"), *args]
        extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        cmd = [str(app / "Phone Trackpad.command"), *args]  # run directly: checks the exec bit too
        extra = {"start_new_session": True}
    log = work / "launcher.log"
    with open(log, "w", encoding="utf-8", errors="replace") as out:
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, **extra)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = log.read_text(encoding="utf-8", errors="replace")
            if "running as" in text or proc.poll() is not None:
                break
            time.sleep(1)
        text = log.read_text(encoding="utf-8", errors="replace")
        print(text.replace("\r", ""))
        if f"Phone Trackpad {version} running as 'PackageCheck' on port {port}" not in text:
            problems.append("the launcher did not start the helper (log above)")
            return
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
                    if b"<title>Phone Trackpad</title>" not in r.read():
                        problems.append("the page is not Phone Trackpad's")
                    break
            except OSError:
                time.sleep(0.1)
        else:
            problems.append("the page did not answer")
        venv = app / "desktop" / ".venv"
        marker = venv / ("Scripts" if os.name == "nt" else "bin") / "requirements.installed"
        if not marker.exists():
            problems.append(f"no install marker at {marker}")
    finally:
        stop(proc)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    zip_path = Path(sys.argv[1]).resolve()
    # The helper's output includes QR code block characters; a Windows console may lack them.
    sys.stdout.reconfigure(errors="replace")
    problems = []
    version = check_contents(zip_path, problems)
    print(f"{zip_path.name}: version {version}, {zip_path.stat().st_size / 1024:.1f} KB")
    if not problems:
        run_launcher(zip_path, version, problems)
    print("PROBLEMS:", "none" if not problems else "")
    for p in problems:
        print(" -", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
