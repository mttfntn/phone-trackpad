"""input_backend: how phone messages become mouse and keyboard events (pynput is faked)."""
import unittest
from unittest import mock

from helpers import input_backend_module


class Base(unittest.TestCase):
    platform = "win32"

    def setUp(self):
        ctx = input_backend_module(self.platform)
        self.mod = ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.b = self.mod.InputBackend()
        self.m = self.b.mouse.log
        self.k = self.b.keyboard.log


class Common(Base):
    def test_move_keeps_subpixel_remainders(self):
        # Exact binary fractions, so the expected result doesn't depend on rounding.
        self.b.move(0.75, -0.25)
        self.assertEqual(self.m, [])
        self.b.move(0.5, -0.5)    # 1.25, -0.75 -> x moves 1, y waits
        self.assertEqual(self.m, [("move", 1, 0)])
        self.b.move(0.75, -0.25)  # 1.0, -1.0
        self.assertEqual(self.m, [("move", 1, 0), ("move", 1, -1)])

    def test_move_large(self):
        self.b.move(10.7, -3.2)
        self.assertEqual(self.m, [("move", 10, -3)])

    def test_down_up_buttons(self):
        self.b.down("right")
        self.b.up("right")
        self.b.down("bogus")
        self.assertEqual([e[0] for e in self.m], ["press", "release", "press"])
        self.assertEqual(self.m[0][1].name, "Button.right")
        self.assertEqual(self.m[2][1].name, "Button.left")

    def test_type_text_newlines_become_enter(self):
        self.b.type_text("ab\n\ncd\n")
        self.assertEqual(self.k, [("type", "ab"), ("tap", self.mod.Key.enter), ("tap", self.mod.Key.enter),
                                  ("type", "cd"), ("tap", self.mod.Key.enter)])

    def test_type_text_empty(self):
        self.b.type_text("")
        self.assertEqual(self.k, [])

    def test_key_named_with_mods(self):
        self.b.key("Enter", ["shift", "ctrl"])
        K = self.mod.Key
        self.assertEqual(self.k, [("press", K.shift), ("press", K.ctrl), ("tap", K.enter),
                                  ("release", K.ctrl), ("release", K.shift)])

    def test_key_char_and_unknown_mod_ignored(self):
        self.b.key("A", ["hyper"])
        self.assertEqual(self.k, [("tap", "char:a")])

    def test_function_keys(self):
        for i in range(1, 13):
            self.b.key(f"f{i}")
        self.assertEqual(len(self.k), 12)

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            self.b.key("notakey")
        self.assertEqual(self.k, [])

    def test_modifiers_released_even_if_tap_fails(self):
        def boom(key):
            raise RuntimeError("tap failed")
        self.b.keyboard.tap = boom
        with self.assertRaises(RuntimeError):
            self.b.key("a", ["alt"])
        self.assertEqual(self.k, [("press", self.mod.Key.alt), ("release", self.mod.Key.alt)])


class Windows(Base):
    platform = "win32"

    def test_cmd_is_ctrl(self):
        self.b.key("c", ["cmd"])
        self.assertEqual(self.k[0], ("press", self.mod.Key.ctrl))

    def test_click_count_clamped(self):
        self.b.click("left", 2)
        self.b.click("right", 9)
        self.b.click("middle", 0)
        self.assertEqual([(e[1].name, e[2]) for e in self.m],
                         [("Button.left", 2), ("Button.right", 3), ("Button.middle", 1)])

    def test_click_bad_count(self):
        with self.assertRaises(ValueError):
            self.b.click("left", "x")

    def test_scroll_passes_fractions(self):
        self.b.scroll(0.25, -0.5)
        self.assertEqual(self.m, [("scroll", 0.25, -0.5)])

    def test_zoom_ctrl_wheel_whole_steps(self):
        self.b.zoom(0.6)
        self.assertEqual(self.m, [])
        self.b.zoom(0.6)   # 1.2 -> one step, 0.2 left
        self.b.zoom(-2.5)  # -2.3 -> two steps down, -0.3 left
        self.assertEqual(self.m, [("scroll", 0, 1), ("scroll", 0, -1), ("scroll", 0, -1)])
        self.assertEqual(self.k, [("press", self.mod.Key.ctrl), ("release", self.mod.Key.ctrl)] * 2)


class Mac(Base):
    platform = "darwin"

    def test_cmd_is_cmd(self):
        self.b.key("c", ["cmd"])
        self.assertEqual(self.k[0], ("press", self.mod.Key.cmd))

    def test_double_click_state_increases(self):
        with mock.patch.object(self.mod.time, "monotonic", side_effect=[1.0, 1.1, 1.2]):
            self.b.click("left", 3)
        # Each press/release pair carries click state 0, 1, 2 (pynput adds one).
        self.assertEqual([e[2] for e in self.m], [0, 0, 1, 1, 2, 2])
        self.assertIsNone(self.b.mouse._click)

    def test_click_state_resets_when_slow_or_moved(self):
        times = iter([1.0, 2.0, 2.1])
        with mock.patch.object(self.mod.time, "monotonic", lambda: next(times)):
            self.b.click("left")
            self.b.click("left")  # too slow: state 1 again
            self.b.mouse.position = (150, 100)
            self.b.click("left")  # moved: state 1 again
        self.assertEqual([e[2] for e in self.m], [0, 0, 0, 0, 0, 0])

    def test_click_state_resets_for_other_button(self):
        with mock.patch.object(self.mod.time, "monotonic", side_effect=[1.0, 1.1]):
            self.b.click("left")
            self.b.click("right")
        self.assertEqual([e[2] for e in self.m], [0, 0, 0, 0])

    def test_scroll_pixels_with_remainder(self):
        q = self.mod._fake_quartz
        self.b.scroll(0.05, 0.05)   # 0.6 px: nothing yet
        self.assertEqual(q.posted, [])
        self.b.scroll(0.05, -0.2)   # x 1.2 -> 1 ; y 0.6 - 2.4 = -1.8 -> -1
        self.assertEqual(q.posted, [("scroll", "pixel", 2, -1, 1)])

    def test_zoom_cmd_plus_minus(self):
        self.b.zoom(2.2)
        self.b.zoom(-1.5)  # 0.2 - 1.5 = -1.3 -> one step out
        K = self.mod.Key
        taps = [e for e in self.k if e[0] == "tap"]
        self.assertEqual(taps, [("tap", "char:="), ("tap", "char:="), ("tap", "char:-")])
        self.assertEqual(self.k[:3], [("press", K.cmd), ("tap", "char:="), ("release", K.cmd)])


if __name__ == "__main__":
    unittest.main()
