"""Focus detection on Windows via UI Automation."""
import uiautomation as auto

EDIT_TYPES = {auto.ControlType.EditControl, auto.ControlType.ComboBoxControl}


class FocusProbe:
    def __enter__(self):
        # UI Automation needs COM initialised on the thread that uses it.
        self._init = auto.UIAutomationInitializerInThread(debug=False)
        return self

    def __exit__(self, *exc):
        del self._init

    def is_editable_focused(self):
        el = auto.GetFocusedControl()
        if el is None:
            return False
        ctype = el.ControlType
        if ctype not in EDIT_TYPES and ctype != auto.ControlType.DocumentControl:
            return False
        value = el.GetPattern(auto.PatternId.ValuePattern)
        if value is not None:
            return not value.IsReadOnly
        # Edits without a Value pattern (e.g. some rich text boxes) are still typeable;
        # documents without one are usually read-only views like a browser page.
        return ctype in EDIT_TYPES
