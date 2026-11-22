"""pairing: PIN checks, wrong-guess limits and saved device tokens (in a temporary folder)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts the app folder on sys.path)
import pairing


class PairingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "cfg"
        self.file = self.dir / "config.json"
        self.old_file = Path(tmp.name) / "old" / "config.json"
        for name, value in (("CONFIG_DIR", self.dir), ("CONFIG_FILE", self.file), ("OLD_CONFIG_FILE", self.old_file)):
            p = mock.patch.object(pairing, name, value, create=True)  # create: older versions lack OLD_CONFIG_FILE
            p.start()
            self.addCleanup(p.stop)
        self.p = pairing.Pairing()

    def wrong_pin(self):
        return "0000" if self.p.pin != "0000" else "1111"

    def test_pin_is_four_digits(self):
        for _ in range(50):
            pin = pairing.Pairing().pin
            self.assertRegex(pin, r"^\d{4}$")

    def test_right_pin_gives_token_and_saves_it(self):
        token = self.p.pair(self.p.pin, "My iPhone")
        self.assertIsInstance(token, str)
        self.assertGreaterEqual(len(token), 30)
        self.assertTrue(self.p.check(token))
        self.assertEqual(self.p.device_name(token), "My iPhone")
        saved = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(saved["tokens"], {token: "My iPhone"})
        # A new helper run reads the same token back.
        again = pairing.Pairing()
        self.assertTrue(again.check(token))

    def test_pin_stays_valid_for_more_phones(self):
        t1 = self.p.pair(self.p.pin, "a")
        t2 = self.p.pair(self.p.pin, "b")
        self.assertNotEqual(t1, t2)
        self.assertTrue(self.p.check(t1) and self.p.check(t2))

    def test_wrong_pin(self):
        self.assertIsNone(self.p.pair(self.wrong_pin(), "x"))
        self.assertIsNone(self.p.pair(None, "x"))
        self.assertIsNone(self.p.pair(1234, "x") if self.p.pin != "1234" else None)
        self.assertFalse(self.file.exists())

    def test_device_name_trimmed_and_defaulted(self):
        t = self.p.pair(self.p.pin, "x" * 100)
        self.assertEqual(len(self.p.device_name(t)), 64)
        t = self.p.pair(self.p.pin, "")
        self.assertEqual(self.p.device_name(t), "phone")

    def test_check_rejects_non_strings_and_unknown(self):
        for bad in (None, 123, "", "nope", ["x"]):
            self.assertFalse(self.p.check(bad))
        self.assertEqual(self.p.device_name("nope"), "?")

    def test_broken_config_starts_empty(self):
        self.dir.mkdir(parents=True)
        self.file.write_text("{not json", encoding="utf-8")
        self.assertFalse(pairing.Pairing().check("anything"))

    def test_phones_paired_before_the_rename_stay_paired(self):
        self.old_file.parent.mkdir(parents=True)
        self.old_file.write_text(json.dumps({"tokens": {"oldtok": "Old iPhone"}}), encoding="utf-8")
        p = pairing.Pairing()
        self.assertTrue(p.check("oldtok"))
        self.assertEqual(json.loads(self.file.read_text(encoding="utf-8"))["tokens"], {"oldtok": "Old iPhone"})
        self.assertTrue(self.old_file.exists(), "old file is copied, not moved")
        # From then on the new file is used, even if the old one changes.
        self.old_file.write_text(json.dumps({"tokens": {}}), encoding="utf-8")
        self.assertTrue(pairing.Pairing().check("oldtok"))

    def test_new_file_wins_over_old(self):
        self.old_file.parent.mkdir(parents=True)
        self.old_file.write_text(json.dumps({"tokens": {"oldtok": "x"}}), encoding="utf-8")
        self.dir.mkdir(parents=True)
        self.file.write_text(json.dumps({"tokens": {"newtok": "y"}}), encoding="utf-8")
        p = pairing.Pairing()
        self.assertTrue(p.check("newtok"))
        self.assertFalse(p.check("oldtok"))

    def test_broken_old_file_ignored(self):
        self.old_file.parent.mkdir(parents=True)
        self.old_file.write_text("{oops", encoding="utf-8")
        self.assertFalse(pairing.Pairing().check("x"))
        self.assertFalse(self.file.exists())

    def test_uses_dot_phone_trackpad_in_home(self):
        if not hasattr(pairing, "OLD_CONFIG_FILE"):
            self.skipTest("version before the rename")
        # patch.dict puts the original module back afterwards.
        with helpers.temp_home() as home, mock.patch.dict(sys.modules):
            fresh = helpers.fresh_import("pairing")
            self.assertEqual(fresh.CONFIG_FILE, home / ".phone-trackpad" / "config.json")
            self.assertEqual(fresh.OLD_CONFIG_FILE, home / ".phonepad" / "config.json")

    def test_ten_wrong_pins_lock_pairing_until_restart(self):
        token = self.p.pair(self.p.pin, "paired before")
        with mock.patch("builtins.print") as out:
            for _ in range(pairing.MAX_FAILURES - 1):
                self.p.pair(self.wrong_pin(), "x")
            self.assertFalse(self.p.locked)
            self.p.pair(self.wrong_pin(), "x")
        self.assertTrue(self.p.locked)
        self.assertIn("restarts", out.call_args[0][0])
        self.assertIsNone(self.p.pair(self.p.pin, "x"), "even the right PIN is refused while locked")
        self.assertTrue(self.p.check(token), "phones paired earlier keep working")
        self.assertFalse(pairing.Pairing().locked, "a restart unlocks, with a new PIN")

    def test_guessing_every_pin_fails(self):
        with mock.patch("builtins.print"):
            hits = [pin for pin in (f"{i:04d}" for i in range(10000)) if self.p.pair(pin, "x")]
        # Only a guess among the first 10 can succeed (10 in 10,000); after that it's locked.
        self.assertLessEqual(len(hits), 1)
        self.assertTrue(self.p.locked)

    def test_non_ascii_pin_is_just_wrong(self):
        for pin in ("é", "١٢٣٤", "12✓4"):
            self.assertIsNone(self.p.pair(pin, "x"))

    def test_right_pin_resets_failure_count(self):
        with mock.patch("builtins.print"):
            for _ in range(pairing.MAX_FAILURES - 1):
                self.p.pair(self.wrong_pin(), "x")
            pin = self.p.pin
            self.assertIsNotNone(self.p.pair(pin, "x"))
            self.p.pair(self.wrong_pin(), "x")
        self.assertEqual(self.p.pin, pin)


if __name__ == "__main__":
    unittest.main()
