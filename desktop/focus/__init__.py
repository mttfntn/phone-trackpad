"""Watches the OS-level focused UI element and reports whether it accepts text."""
import sys
import threading
import time

POLL_INTERVAL = 0.2


def start_focus_watcher(on_change):
    """Starts a daemon thread that calls on_change(editable: bool) whenever editability changes.

    on_change is called from the watcher thread. Returns False if no watcher is available.
    """
    if sys.platform == "win32":
        from .windows import FocusProbe
    elif sys.platform == "darwin":
        from .mac import FocusProbe
    else:
        return False

    def loop():
        probe = FocusProbe()
        with probe:
            last = None
            while True:
                try:
                    editable = probe.is_editable_focused()
                except Exception:  # transient errors while windows open/close
                    editable = False
                if editable != last:
                    last = editable
                    on_change(editable)
                time.sleep(POLL_INTERVAL)

    threading.Thread(target=loop, name="focus-watcher", daemon=True).start()
    return True
