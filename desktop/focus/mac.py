"""Focus detection on macOS via the Accessibility API."""
import Quartz
from ApplicationServices import (
    AXIsProcessTrusted,
    AXUIElementCopyAttributeValue,
    AXUIElementCopyElementAtPosition,
    AXUIElementCreateSystemWide,
    AXUIElementIsAttributeSettable,
)

TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}


def _attr(el, name):
    err, value = AXUIElementCopyAttributeValue(el, name, None)
    return value if err == 0 else None


def _is_editable(el):
    role = _attr(el, "AXRole")
    if role in TEXT_ROLES:
        return True
    # contenteditable regions and custom editors usually expose a settable AXValue.
    if role in ("AXWebArea", "AXGroup"):
        err, settable = AXUIElementIsAttributeSettable(el, "AXValue", None)
        return err == 0 and bool(settable)
    return False


class FocusProbe:
    """Readings for focus.start_focus_watcher; used as a context manager on the watcher thread."""

    def __enter__(self):
        if not AXIsProcessTrusted():
            print("Accessibility permission missing: keyboard pop-up and input injection won't work.\n"
                  "Grant it in System Settings > Privacy & Security > Accessibility.")
        self._system = AXUIElementCreateSystemWide()
        return self

    def __exit__(self, *exc):
        pass

    def is_editable_focused(self):
        el = _attr(self._system, "AXFocusedUIElement")
        return el is not None and _is_editable(el)

    def cursor_position(self):
        # Global top-left-origin coordinates, the same space the Accessibility API uses.
        loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return (round(loc.x), round(loc.y))

    def is_editable_at(self, x, y):
        err, el = AXUIElementCopyElementAtPosition(self._system, x, y, None)
        # The point often lands on static text inside the field, so look a little way up.
        for _ in range(3):
            if err != 0 or el is None:
                return False
            if _is_editable(el):
                return True
            el = _attr(el, "AXParent")
        return False
