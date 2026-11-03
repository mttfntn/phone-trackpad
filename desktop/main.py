"""PhonePad desktop helper: serves the PhonePad phone page and lets it control this computer."""
import argparse
import asyncio
import io
import socket
import sys

from discovery import Advertiser
from focus import start_focus_watcher
from pairing import Pairing
from server import OS_NAME, PhonePadServer
from volume import FakeVolume, create_volume


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
    server = PhonePadServer(backend, pairing, name, volume)
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
    await advertiser.start()

    ip = advertiser.addresses[0] if advertiser.addresses else "127.0.0.1"
    url = f"http://{ip}:{args.port}/#pin={pairing.pin}"
    print(f"PhonePad running as {name!r} on port {args.port}")
    print(f"On your phone (same Wi-Fi), scan the QR code or open:\n  {url}")
    print_qr(url)
    print(f"Pairing PIN: {pairing.pin}")
    try:
        await server.run(port=args.port)
    finally:
        volume_task.cancel()
        await advertiser.stop()


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


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
    # Checked up front so a second copy says so plainly instead of printing a QR code and a traceback.
    if not port_free(args.port):
        print(f"PhonePad is already running (port {args.port} is in use).\n"
              "Close the other PhonePad window first, or start this one with --port 8766.")
        sys.exit(1)
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
