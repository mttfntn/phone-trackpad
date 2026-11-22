"""Phone Trackpad desktop helper: serves the phone page and lets it control this computer."""
import argparse
import asyncio
import io
import os
import socket
import sys
import urllib.request

from version import MIN_PYTHON, VERSION

# Checked before the other imports, which may use newer Python syntax or libraries.
if sys.version_info < MIN_PYTHON:
    sys.exit(f"Phone Trackpad needs Python {'.'.join(map(str, MIN_PYTHON))} or newer; "
             f"this is Python {sys.version.split()[0]}. Get it from https://www.python.org/downloads/")

from discovery import Advertiser  # noqa: E402
from focus import start_focus_watcher  # noqa: E402
from pairing import Pairing  # noqa: E402
from server import OS_NAME, TrackpadServer  # noqa: E402
from volume import FakeVolume, create_volume  # noqa: E402


class DryRunBackend:
    """Logs input actions instead of performing them, for testing the phone page safely."""

    def __init__(self, on_click=None):
        self.on_click = on_click

    def __getattr__(self, name):
        def log(*args):
            print(f"[dry-run] {name}{args}")
            if name == "click" and self.on_click:
                self.on_click()
        return log


def print_qr(url):
    try:
        import qrcode
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    try:
        sys.stdout.write(buf.getvalue())
    except UnicodeEncodeError:
        pass  # console can't show the block characters; the URL is printed anyway


async def amain(args):
    name = args.name or socket.gethostname().split(".")[0]
    pairing = Pairing()
    loop = asyncio.get_running_loop()

    if args.dry_run:
        # With --simulate-focus every click toggles a fake text-field focus, and the cursor
        # "hovers" a text field whenever none is focused, to test the keyboard pop-up.
        def toggle():
            server.set_focus(not server.editable)
            server.set_hover(not server.editable)

        backend = DryRunBackend(toggle if args.simulate_focus else None)
        volume = FakeVolume()
    else:
        from input_backend import InputBackend
        backend = InputBackend()
        volume = create_volume()
    server = TrackpadServer(backend, pairing, name, volume)
    volume_task = asyncio.ensure_future(server.poll_volume())
    if args.simulate_focus:
        server.set_hover(True)

    if not args.no_focus and not args.simulate_focus:
        def on_focus(editable):
            if args.verbose:
                print(f"focus editable={editable}")
            loop.call_soon_threadsafe(server.set_focus, editable)

        def on_hover(editable):
            if args.verbose:
                print(f"hover editable={editable}")
            loop.call_soon_threadsafe(server.set_hover, editable)

        if not start_focus_watcher(on_focus, on_hover):
            print("Keyboard pop-up isn't supported on this OS.")

    advertiser = Advertiser(name, args.port, OS_NAME)
    # Announcing on Bonjour takes about 1.2 s (mDNS probing); the link doesn't depend on it,
    # so it runs alongside instead of delaying the link and the server.
    advertising = asyncio.ensure_future(advertiser.start())
    advertising.add_done_callback(_report_advertise_failure)

    ip = advertiser.addresses[0] if advertiser.addresses else "127.0.0.1"
    url = f"http://{ip}:{args.port}/#pin={pairing.pin}"
    print(f"Phone Trackpad {VERSION} running as {name!r} on port {args.port}")
    print(f"On your phone (same Wi-Fi), scan the QR code or open:\n  {url}")
    print_qr(url)
    print(f"Pairing PIN: {pairing.pin}")
    try:
        await server.run(port=args.port)
    finally:
        volume_task.cancel()
        advertising.cancel()
        await asyncio.gather(advertising, return_exceptions=True)
        await advertiser.stop()


def _report_advertise_failure(task):
    if not task.cancelled() and task.exception():
        print(f"Bonjour announcement failed ({task.exception()}); the link above still works.")


def port_free(port):
    """True if the server could listen on `port`."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":
            # Same option the server's own socket uses (asyncio sets it outside Windows). Without
            # it, connections from a phone that just disconnected (TIME_WAIT) made a restart look
            # like the port was taken.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def is_trackpad(port):
    """True if the program answering on this port is another copy of Phone Trackpad."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
            return b"<title>Phone Trackpad</title>" in r.read(4096)
    except (OSError, ValueError):
        return False


def next_free_port(port, tries=20):
    for candidate in range(port + 1, port + 1 + tries):
        if port_free(candidate):
            return candidate
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--name", help="name shown on the phone (default: hostname)")
    p.add_argument("--no-focus", action="store_true", help="disable keyboard pop-up on text fields")
    p.add_argument("--dry-run", action="store_true", help="log input instead of controlling the computer")
    p.add_argument("--simulate-focus", action="store_true", help="with --dry-run: each click toggles text focus")
    p.add_argument("-v", "--verbose", action="store_true", help="log focus changes")
    args = p.parse_args()
    if args.simulate_focus and not args.dry_run:
        p.error("--simulate-focus needs --dry-run")
    if sys.platform not in ("darwin", "win32") and not args.dry_run:
        # --dry-run never touches this computer, so it still runs anywhere (handy for testing).
        sys.exit("Phone Trackpad controls Windows and macOS only; this system isn't supported.")
    # Checked up front so a second copy says so plainly instead of printing a QR code and a traceback.
    if not port_free(args.port):
        if is_trackpad(args.port):
            print(f"Phone Trackpad is already running (port {args.port} is in use).\n"
                  f"Close the other Phone Trackpad window first, or start this one with --port {args.port + 1}.")
            sys.exit(1)
        # Some other program holds the port: move to the next free one instead of stopping.
        free = next_free_port(args.port)
        if free is None:
            print(f"Port {args.port} and the 20 after it are in use. Pick one with --port.")
            sys.exit(1)
        print(f"Port {args.port} is used by another program, so Phone Trackpad is using port {free} instead.\n"
              "The link below has the new port; links saved on the phone with the old port won't work.")
        args.port = free
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
