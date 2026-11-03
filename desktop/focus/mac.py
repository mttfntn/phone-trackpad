"""Focus detection on macOS via the Accessibility API."""
from ApplicationServices import (
    AXIsProcessTrusted,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateSystemWide,
    AXUIElementIsAttributeSettable,
)

TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}


class FocusProbe:
    def __enter__(self):
        if not AXIsProcessTrusted():
            print("Accessibility permission missing: keyboard auto pop-up and input injection won't work.\n"
                  "Grant it in System Settings > Privacy & Security > Accessibility.")
        self._system = AXUIElementCreateSystemWide()
        return self

    def __exit__(self, *exc):
        pass

    def _attr(self, el, name):
        err, value = AXUIElementCopyAttributeValue(el, name, None)
        return value if err == 0 else None

    def is_editable_focused(self):
        el = self._attr(self._system, "AXFocusedUIElement")
        if el is None:
            return False
        role = self._attr(el, "AXRole")
        if role in TEXT_ROLES:
            return True
        # contenteditable regions and custom editors usually expose a settable AXValue.
        if role in ("AXWebArea", "AXGroup"):
            err, settable = AXUIElementIsAttributeSettable(el, "AXValue", None)
            return err == 0 and bool(settable)
        return False
