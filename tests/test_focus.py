"""focus: the watcher loop (with a scripted probe) and the Windows and macOS text-field checks
(with fake uiautomation / ApplicationServices / Quartz modules, so both run on either OS)."""
import sys
import threading
import unittest
from unittest import mock

from helpers import fake_modules, fresh_import, module


class StopLoop(BaseException):
    pass


class FakeTime:
    """Replaces the time module inside focus: counts loop rounds and stops after `rounds`."""
    def __init__(self, rounds, step=0.2):
        self.rounds, self.step, self.now, self.done = rounds, step, 0.0, 0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.done += 1
        self.now += self.step
        if self.done >= self.rounds:
            raise SystemExit  # ends the watcher thread quietly


def scripted_probe(focused, positions=None, at=None):
    """A FocusProbe class whose readings come from lists (an Exception item is raised)."""
    focused = list(focused)
    positions = list(positions or [])
    at = list(at or [])
    calls = []

    def take(seq, default):
        v = seq.pop(0) if seq else default
        if isinstance(v, Exception):
            raise v
        return v

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def is_editable_focused(self):
            return take(focused, False)

        def cursor_position(self):
            return take(positions, (0, 0))

        def is_editable_at(self, x, y):
            calls.append((x, y))
            return take(at, False)

    Probe.at_calls = calls
    return Probe


def run_watcher(probe, rounds, with_hover=True, platform="darwin", step=0.2):
    focus = fresh_import("focus")
    events = []
    fake_time = FakeTime(rounds, step)
    probe_mod = module("focus.x", FocusProbe=probe)
    name = "focus.mac" if platform == "darwin" else "focus.windows"
    with mock.patch.object(sys, "platform", platform), fake_modules(**{name.replace(".", "__"): probe_mod}), \
            mock.patch.object(focus, "time", fake_time):
        ok = focus.start_focus_watcher(lambda e: events.append(("focus", e)),
                                       (lambda e: events.append(("hover", e))) if with_hover else None)
        for t in threading.enumerate():
            if t.name == "focus-watcher":
                t.join(5)
    return ok, events


class WatcherTest(unittest.TestCase):
    def test_unsupported_platform(self):
        focus = fresh_import("focus")
        with mock.patch.object(sys, "platform", "linux"):
            self.assertFalse(focus.start_focus_watcher(lambda e: None))

    def test_focus_gained_at_once_lost_after_two_readings(self):
        ok, ev = run_watcher(scripted_probe([True, False, True, False, False, False]), 6, with_hover=False)
        self.assertTrue(ok)
        self.assertEqual(ev, [("focus", True), ("focus", False)])

    def test_initial_false_reported_after_two_readings(self):
        _, ev = run_watcher(scripted_probe([False, False, False]), 3, with_hover=False)
        self.assertEqual(ev, [("focus", False)])

    def test_errors_count_as_no_reading(self):
        _, ev = run_watcher(scripted_probe([True, RuntimeError(), False, RuntimeError(), False]), 5,
                            with_hover=False)
        # An error between two False readings breaks the streak.
        self.assertEqual(ev, [("focus", True)])

    def test_windows_probe_is_used_on_windows(self):
        _, ev = run_watcher(scripted_probe([True]), 1, with_hover=False, platform="win32")
        self.assertEqual(ev, [("focus", True)])

    def test_hover_checked_when_cursor_moves(self):
        probe = scripted_probe([False] * 5, positions=[(1, 1), (1, 1), (2, 2), (2, 2), (3, 3)],
                               at=[True, True, False])
        _, ev = run_watcher(probe, 5)
        self.assertEqual(probe.at_calls, [(1, 1), (2, 2), (3, 3)])
        self.assertEqual([e for e in ev if e[0] == "hover"], [("hover", True), ("hover", False)])

    def test_still_cursor_rechecked_now_and_then(self):
        probe = scripted_probe([False] * 10, positions=[(5, 5)] * 10, at=[False, True])
        _, ev = run_watcher(probe, 10)
        self.assertEqual(len(probe.at_calls), 2)  # 0.2 s rounds, re-check after more than 1 s
        self.assertIn(("hover", True), ev)

    def test_no_cursor_reading_skips_hover(self):
        probe = scripted_probe([False] * 3, positions=[RuntimeError(), None, RuntimeError()])
        _, ev = run_watcher(probe, 3)
        self.assertEqual(probe.at_calls, [])
        self.assertEqual([e for e in ev if e[0] == "hover"], [])


# ---------- Windows text-field check (fake uiautomation) ----------

class FakeCT:
    EditControl, ComboBoxControl, DocumentControl, ButtonControl, TextControl = range(5)


class FakeControl:
    def __init__(self, ctype, value=None, parent=None):
        self.ControlType = ctype
        self._value = value
        self._parent = parent

    def GetPattern(self, pid):
        return self._value

    def GetParentControl(self):
        return self._parent


def fake_uiautomation(focused=None, at=None):
    return module(
        "uiautomation",
        ControlType=FakeCT,
        PatternId=module("PatternId", ValuePattern=1),
        GetFocusedControl=lambda: focused,
        ControlFromPoint=lambda x, y: at,
        GetCursorPos=lambda: (10, 20),
        UIAutomationInitializerInThread=lambda debug=False: object(),
    )


class Ro:
    def __init__(self, ro):
        self.IsReadOnly = ro


class WindowsProbeTest(unittest.TestCase):
    def probe(self, **kw):
        with fake_modules(uiautomation=fake_uiautomation(**kw)):
            win = fresh_import("focus.windows")
            with win.FocusProbe() as p:
                return win, p, p.is_editable_focused(), p.is_editable_at(1, 2), p.cursor_position()

    def test_kinds(self):
        cases = [
            (FakeControl(FakeCT.EditControl, Ro(False)), True),
            (FakeControl(FakeCT.EditControl, Ro(True)), False),
            (FakeControl(FakeCT.EditControl), True),          # rich edit without Value pattern
            (FakeControl(FakeCT.ComboBoxControl), True),
            (FakeControl(FakeCT.DocumentControl, Ro(False)), True),
            (FakeControl(FakeCT.DocumentControl), False),     # read-only page
            (FakeControl(FakeCT.ButtonControl, Ro(False)), False),
            (None, False),
        ]
        for el, want in cases:
            _, _, focused, _, _ = self.probe(focused=el)
            self.assertEqual(focused, want, el and el.ControlType)

    def test_at_point_looks_up_three_levels(self):
        edit = FakeControl(FakeCT.EditControl, Ro(False))
        t3 = FakeControl(FakeCT.TextControl, parent=FakeControl(FakeCT.TextControl, parent=edit))
        _, _, _, hit, pos = self.probe(at=t3)
        self.assertTrue(hit)
        self.assertEqual(pos, (10, 20))
        too_deep = FakeControl(FakeCT.TextControl, parent=t3)
        self.assertFalse(self.probe(at=too_deep)[3])
        self.assertFalse(self.probe(at=None)[3])


# ---------- macOS text-field check (fake ApplicationServices / Quartz) ----------

class El:
    def __init__(self, role, settable=None, parent=None):
        self.role, self.settable, self.parent = role, settable, parent


def fake_appservices(focused=None, at=None, trusted=True):
    def copy_attr(el, name, _):
        if el == "system" and name == "AXFocusedUIElement":
            return (0, focused) if focused else (-25212, None)
        if name == "AXRole":
            return 0, el.role
        if name == "AXParent":
            return (0, el.parent) if el.parent else (-25212, None)
        return -1, None

    def settable(el, name, _):
        return (0, el.settable) if el.settable is not None else (-25205, False)

    return module(
        "ApplicationServices",
        AXIsProcessTrusted=lambda: trusted,
        AXUIElementCopyAttributeValue=copy_attr,
        AXUIElementCopyElementAtPosition=lambda s, x, y, _: (0, at) if at else (-25200, None),
        AXUIElementCreateSystemWide=lambda: "system",
        AXUIElementIsAttributeSettable=settable,
    )


class FakeLoc:
    x, y = 10.6, 20.2


fake_quartz = module("Quartz", CGEventCreate=lambda src: "ev", CGEventGetLocation=lambda ev: FakeLoc())


class MacProbeTest(unittest.TestCase):
    def probe(self, **kw):
        with fake_modules(ApplicationServices=fake_appservices(**kw), Quartz=fake_quartz), \
                mock.patch("builtins.print") as out:
            mac = fresh_import("focus.mac")
            with mac.FocusProbe() as p:
                return p.is_editable_focused(), p.is_editable_at(1, 2), p.cursor_position(), out

    def test_kinds(self):
        cases = [
            (El("AXTextField"), True), (El("AXTextArea"), True), (El("AXComboBox"), True),
            (El("AXSearchField"), True), (El("AXWebArea", settable=True), True),
            (El("AXWebArea", settable=False), False), (El("AXGroup", settable=True), True),
            (El("AXGroup"), False), (El("AXButton", settable=True), False), (None, False),
        ]
        for el, want in cases:
            self.assertEqual(self.probe(focused=el)[0], want, el and el.role)

    def test_at_point_looks_up_three_levels(self):
        field = El("AXTextField")
        s = El("AXStaticText", parent=El("AXStaticText", parent=field))
        focused, hit, pos, _ = self.probe(at=s)
        self.assertTrue(hit)
        self.assertEqual(pos, (11, 20))
        self.assertFalse(self.probe(at=El("AXStaticText", parent=s))[1])
        self.assertFalse(self.probe(at=None)[1])

    def test_warns_without_accessibility_permission(self):
        out = self.probe(trusted=False)[3]
        self.assertIn("Accessibility", out.call_args[0][0])
        self.assertFalse(self.probe(trusted=True)[3].called)


if __name__ == "__main__":
    unittest.main()
