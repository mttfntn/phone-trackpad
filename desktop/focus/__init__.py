"""Watches the OS-level UI for text fields: the focused element, and the element under the cursor."""
import sys
import threading
import time

POLL_INTERVAL = 0.2
HOVER_RECHECK_S = 1.0  # re-check a still cursor now and then, in case the window under it changed


def start_focus_watcher(on_focus, on_hover=None):
    """Starts a daemon thread reporting editability changes.

    on_focus(editable) fires when the focused element starts or stops accepting text.
    on_hover(editable) fires when the element under the cursor does; the phone uses it to
    open its keyboard on the same tap that clicks into a text field.
    Both are called from the watcher thread. Returns False if no watcher is available.
    """
    if sys.platform == "win32":
        from .windows import FocusProbe
    elif sys.platform == "darwin":
        from .mac import FocusProbe
    else:
        return False

    def check(fn, *args):
        try:
            return fn(*args)
        except Exception:  # transient errors while windows open/close: treat as "no reading"
            return None

    def loop():
        with FocusProbe() as probe:
            last_focus = last_hover = None
            last_pos, last_hover_check = None, 0.0
            false_streak = 0
            while True:
                editable = check(probe.is_editable_focused)
                # Report gaining focus at once, but losing it only after two readings in a row,
                # so a momentary glitch doesn't make the phone keyboard flicker.
                false_streak = false_streak + 1 if editable is False else 0
                if editable and last_focus is not True:
                    last_focus = True
                    on_focus(True)
                elif false_streak >= 2 and last_focus is not False:
                    last_focus = False
                    on_focus(False)

                if on_hover:
                    pos = check(probe.cursor_position)
                    now = time.monotonic()
                    if pos and (pos != last_pos or now - last_hover_check > HOVER_RECHECK_S):
                        last_pos, last_hover_check = pos, now
                        hover = check(probe.is_editable_at, *pos)
                        if hover is not None and hover != last_hover:
                            last_hover = hover
                            on_hover(hover)
                time.sleep(POLL_INTERVAL)

    threading.Thread(target=loop, name="focus-watcher", daemon=True).start()
    return True
