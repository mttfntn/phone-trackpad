"""Injects mouse and keyboard input on the local machine using pynput.

Two things work differently on macOS: clicks set a click count (through pynput's private
`_click` field), so that quick clicks become double clicks, and scrolling posts pixel-based
Quartz scroll events directly, for smooth scrolling. On macOS all of this needs the
Accessibility permission for the app that runs the helper (Terminal, for the launcher).
"""
import sys
import time

from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode

IS_MAC = sys.platform == "darwin"

# Pixels scrolled per wheel step on macOS (Windows takes fractional wheel steps natively).
MAC_SCROLL_PX = 12
DOUBLE_CLICK_S = 0.4

BUTTONS = {"left": mouse.Button.left, "right": mouse.Button.right, "middle": mouse.Button.middle}

NAMED_KEYS = {
    "backspace": Key.backspace, "enter": Key.enter, "tab": Key.tab, "esc": Key.esc,
    "delete": Key.delete, "space": Key.space, "up": Key.up, "down": Key.down,
    "left": Key.left, "right": Key.right, "home": Key.home, "end": Key.end,
    "pageup": Key.page_up, "pagedown": Key.page_down,
    **{f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)},
}

# "cmd" is the platform's primary shortcut modifier: Cmd on Mac, Ctrl on Windows.
MODIFIERS = {
    "ctrl": Key.ctrl, "alt": Key.alt, "shift": Key.shift,
    "cmd": Key.cmd if IS_MAC else Key.ctrl,
}


class InputBackend:
    """The real input backend used by server.TrackpadServer (main.DryRunBackend is the fake)."""

    def __init__(self):
        self.mouse = mouse.Controller()
        self.keyboard = keyboard.Controller()
        # Sub-pixel remainders so slow finger movements aren't lost to rounding.
        self._rem_x = 0.0
        self._rem_y = 0.0
        self._scroll_rem_x = 0.0
        self._scroll_rem_y = 0.0
        self._last_click = None
        self._zoom_rem = 0.0

    def move(self, dx, dy):
        """Moves the cursor by (dx, dy) pixels, carrying fractions over to the next move."""
        self._rem_x += dx
        self._rem_y += dy
        ix, iy = int(self._rem_x), int(self._rem_y)
        if ix or iy:
            self._rem_x -= ix
            self._rem_y -= iy
            self.mouse.move(ix, iy)

    def click(self, button="left", count=1):
        """Clicks `button` ("left", "right" or "middle") 1 to 3 times."""
        btn = BUTTONS.get(button, mouse.Button.left)
        count = max(1, min(int(count), 3))
        if IS_MAC:
            for _ in range(count):
                self._click_mac(btn)
        else:
            # Windows turns quick successive clicks into double clicks by itself.
            self.mouse.click(btn, count)

    def _click_mac(self, btn):
        # macOS only sees a double click if the events carry an increasing click state,
        # so continue the sequence when clicks come quickly at the same spot.
        now = time.monotonic()
        x, y = self.mouse.position
        last = self._last_click
        if last and last[0] == btn and now - last[1] < DOUBLE_CLICK_S and abs(x - last[2]) + abs(y - last[3]) < 6:
            state = last[4] + 1
        else:
            state = 1
        self._last_click = (btn, now, x, y, state)
        # pynput's darwin controller stamps press/release with _click when it isn't None.
        self.mouse._click = state - 1
        try:
            self.mouse.press(btn)
            self.mouse.release(btn)
        finally:
            self.mouse._click = None

    def down(self, button="left"):
        """Presses a button and keeps it down (start of a drag)."""
        self.mouse.press(BUTTONS.get(button, mouse.Button.left))

    def up(self, button="left"):
        """Releases a button (end of a drag)."""
        self.mouse.release(BUTTONS.get(button, mouse.Button.left))

    def scroll(self, dx, dy):
        """Scrolls by wheel steps (fractions allowed); dy > 0 scrolls up, dx > 0 right."""
        if IS_MAC:
            self._scroll_mac(dx, dy)
        else:
            # pynput's win32 backend multiplies by WHEEL_DELTA, so fractions give smooth scrolling.
            self.mouse.scroll(dx, dy)

    def _scroll_mac(self, dx, dy):
        import Quartz

        self._scroll_rem_x += dx * MAC_SCROLL_PX
        self._scroll_rem_y += dy * MAC_SCROLL_PX
        px, py = int(self._scroll_rem_x), int(self._scroll_rem_y)
        if not (px or py):
            return
        self._scroll_rem_x -= px
        self._scroll_rem_y -= py
        event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 2, py, px)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def zoom(self, steps):
        """Pinch zoom: positive zooms in. Sent as whole steps so apps zoom by their usual increments."""
        self._zoom_rem += steps
        n = int(self._zoom_rem)
        if not n:
            return
        self._zoom_rem -= n
        if IS_MAC:
            # Cmd+= / Cmd+- is what browsers, Finder, Preview and most Mac apps use for zoom.
            key = "=" if n > 0 else "-"
            for _ in range(abs(n)):
                self.key(key, ["cmd"])
        else:
            # Ctrl+mouse wheel zooms in browsers, Office, Explorer and most Windows apps.
            with self.keyboard.pressed(Key.ctrl):
                for _ in range(abs(n)):
                    self.mouse.scroll(0, 1 if n > 0 else -1)

    def type_text(self, s):
        """Types `s` as text (any Unicode character)."""
        # Send newlines as real Enter presses; everything else goes through unicode typing.
        for i, line in enumerate(s.split("\n")):
            if i:
                self.keyboard.tap(Key.enter)
            if line:
                self.keyboard.type(line)

    def key(self, name, mods=()):
        """Taps one key (a NAMED_KEYS name or one character) while holding `mods`.

        Raises ValueError for an unknown key; unknown modifiers are ignored.
        """
        name = str(name).lower()
        if name in NAMED_KEYS:
            target = NAMED_KEYS[name]
        elif len(name) == 1:
            target = KeyCode.from_char(name)
        else:
            raise ValueError(f"unknown key {name!r}")
        held = [MODIFIERS[m] for m in mods if m in MODIFIERS]
        for m in held:
            self.keyboard.press(m)
        try:
            self.keyboard.tap(target)
        finally:
            for m in reversed(held):
                self.keyboard.release(m)
