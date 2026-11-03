"""Focus detection on Windows via UI Automation."""
import uiautomation as auto

EDIT_TYPES = {auto.ControlType.EditControl, auto.ControlType.ComboBoxControl}


def _is_editable(el):
    ctype = el.ControlType
    if ctype not in EDIT_TYPES and ctype != auto.ControlType.DocumentControl:
        return False
    value = el.GetPattern(auto.PatternId.ValuePattern)
    if value is not None:
        return not value.IsReadOnly
    # Edits without a Value pattern (e.g. some rich text boxes) are still typeable;
    # documents without one are usually read-only views like a browser page.
    return ctype in EDIT_TYPES


class FocusProbe:
    def __enter__(self):
        # UI Automation needs COM initialised on the thread that uses it.
        self._init = auto.UIAutomationInitializerInThread(debug=False)
        return self

    def __exit__(self, *exc):
        del self._init

    def is_editable_focused(self):
        el = auto.GetFocusedControl()
        return el is not None and _is_editable(el)

    def cursor_position(self):
        # Same coordinate space as ControlFromPoint, whatever the display scaling.
        return auto.GetCursorPos()

    def is_editable_at(self, x, y):
        el = auto.ControlFromPoint(x, y)
        # The point often lands on a text child inside the field, so look a little way up.
        for _ in range(3):
            if el is None:
                return False
            if _is_editable(el):
                return True
            el = el.GetParentControl()
        return False
