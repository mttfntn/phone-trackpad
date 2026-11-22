"""Shared test helpers: where the app code lives, fake platform modules, and a throwaway home folder.

The app code is imported from `desktop/` in this checkout, or from the folder in the
APP_ROOT environment variable (used to run the same tests on an older copy, e.g. a git
worktree of the previous release). Nothing here touches the real home folder, the real
mouse or keyboard, or a running copy of the app.
"""
import contextlib
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
APP_DIR = Path(os.environ.get("APP_ROOT") or REPO / "desktop").resolve()

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@contextlib.contextmanager
def temp_home():
    """Points HOME (and USERPROFILE on Windows) at an empty temporary folder."""
    with tempfile.TemporaryDirectory() as home:
        with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):
            yield Path(home)


def module(name, **attrs):
    """A stand-in module with the given attributes."""
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


@contextlib.contextmanager
def fake_modules(**modules):
    """Temporarily installs stand-in modules (names use __ for dots: pynput__keyboard)."""
    entries = {name.replace("__", "."): m for name, m in modules.items()}
    with mock.patch.dict(sys.modules, entries):
        yield


def fresh_import(name):
    """Imports `name` again, so it binds to whatever fake modules are installed now."""
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[key]
    __import__(name)
    return sys.modules[name]


# ---------- fake pynput ----------

class _Named:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


class FakeKey:
    """Mimics pynput.keyboard.Key: attributes are named key objects."""
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = _Named(f"Key.{name}")
        setattr(self, name, value)
        return value


class FakeKeyCode:
    @staticmethod
    def from_char(c):
        return f"char:{c}"


class FakeButton:
    left = _Named("Button.left")
    right = _Named("Button.right")
    middle = _Named("Button.middle")


class FakeMouseController:
    def __init__(self):
        self.log = []
        self.position = (100, 100)
        self._click = None  # pynput's darwin controller reads this for the click state

    def move(self, dx, dy):
        self.log.append(("move", dx, dy))

    def click(self, button, count=1):
        self.log.append(("click", button, count))

    def press(self, button):
        self.log.append(("press", button, self._click))

    def release(self, button):
        self.log.append(("release", button, self._click))

    def scroll(self, dx, dy):
        self.log.append(("scroll", dx, dy))


class FakeKeyboardController:
    def __init__(self):
        self.log = []

    def press(self, key):
        self.log.append(("press", key))

    def release(self, key):
        self.log.append(("release", key))

    def tap(self, key):
        self.log.append(("tap", key))

    def type(self, s):
        self.log.append(("type", s))

    @contextlib.contextmanager
    def pressed(self, *keys):
        for k in keys:
            self.press(k)
        try:
            yield
        finally:
            for k in reversed(keys):
                self.release(k)


class FakeQuartz:
    """Records CGEventPost calls instead of posting events."""
    kCGScrollEventUnitPixel = "pixel"
    kCGHIDEventTap = "hid"

    def __init__(self):
        self.posted = []

    def CGEventCreateScrollWheelEvent(self, source, unit, count, dy, dx):
        return ("scroll", unit, count, dy, dx)

    def CGEventPost(self, tap, event):
        self.posted.append(event)


def fake_pynput():
    key = FakeKey()
    keyboard_mod = module("pynput.keyboard", Key=key, KeyCode=FakeKeyCode, Controller=FakeKeyboardController)
    mouse_mod = module("pynput.mouse", Button=FakeButton, Controller=FakeMouseController)
    return module("pynput", keyboard=keyboard_mod, mouse=mouse_mod), keyboard_mod, mouse_mod


@contextlib.contextmanager
def input_backend_module(platform):
    """Imports input_backend against fake pynput (and fake Quartz), as if on `platform`."""
    pynput, kb, ms = fake_pynput()
    quartz = FakeQuartz()
    with fake_modules(pynput=pynput, pynput__keyboard=kb, pynput__mouse=ms, Quartz=quartz), \
            mock.patch.object(sys, "platform", platform):
        mod = fresh_import("input_backend")
        mod._fake_quartz = quartz
        yield mod
    sys.modules.pop("input_backend", None)
