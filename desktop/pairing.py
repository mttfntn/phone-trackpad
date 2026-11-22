"""PIN pairing and persisted device tokens."""
import json
import os
import secrets
from pathlib import Path

CONFIG_DIR = Path.home() / ".phone-trackpad"
CONFIG_FILE = CONFIG_DIR / "config.json"
# Where versions before the rename (when the app was called PhonePad) kept paired phones.
OLD_CONFIG_FILE = Path.home() / ".phonepad" / "config.json"
MAX_FAILURES = 10


class Pairing:
    def __init__(self):
        self.pin = self._new_pin()
        self._failures = 0
        self._config = self._load()

    @staticmethod
    def _new_pin():
        return f"{secrets.randbelow(10000):04d}"

    def _load(self):
        path = CONFIG_FILE
        if not path.exists() and OLD_CONFIG_FILE.exists():
            # Phones paired with PhonePad stay paired; the old file is copied, not moved.
            path = OLD_CONFIG_FILE
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"tokens": {}}
        if path is OLD_CONFIG_FILE:
            self._config = config
            self._save()
        return config

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._config, indent=2), encoding="utf-8")
        os.replace(tmp, CONFIG_FILE)

    def pair(self, pin, device):
        """Returns a new token if the PIN matches, else None.

        Too many wrong guesses rotate the PIN so it can't be brute-forced.
        """
        if secrets.compare_digest(str(pin), self.pin):
            token = secrets.token_urlsafe(24)
            self._config["tokens"][token] = str(device)[:64] or "iPhone"
            self._save()
            self._failures = 0
            return token
        self._failures += 1
        if self._failures >= MAX_FAILURES:
            self.pin = self._new_pin()
            self._failures = 0
            print(f"Too many wrong PINs. New pairing PIN: {self.pin}")
        return None

    def check(self, token):
        return isinstance(token, str) and token in self._config["tokens"]

    def device_name(self, token):
        return self._config["tokens"].get(token, "?")
