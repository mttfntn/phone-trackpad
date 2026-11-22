# AGENTS.md: Phone Trackpad

Phone (iPhone/Android) as a wireless trackpad and keyboard for Windows and macOS. A Python helper
(`desktop/`) serves a web page (`desktop/web/`) and a WebSocket on one port, and injects input
with pynput. Formerly "PhonePad". Humans: see HANDOVER.md.

## Commands (repo root; use the Python that has desktop/requirements.txt installed)

```
desktop/.venv/bin/python tests/run_tests.py                # 166 checks (121 Python + 45 page), must end "0 failed"
python tests/run_tests.py --python-only                    # no Node.js
python tests/run_tests.py --app-root OLD/desktop           # same suite on another copy
python tests/probe_behaviour.py old.json --app-root OLD/desktop
python tests/probe_behaviour.py new.json
python tests/compare_probes.py old.json new.json           # "0 differences" unless behaviour changed on purpose
python tools/build_package.py                              # -> dist/phone-trackpad-<ver>.zip (20 files, ~44 KB)
python tests/check_package.py dist/phone-trackpad-*.zip    # unzip + real launcher + page; "PROBLEMS: none"
python desktop/main.py --dry-run [--simulate-focus] [--no-focus] [--port N]   # safe manual run
```

Never test against the user's running helper or real `~/.phone-trackpad`: tests set HOME to a temp
folder and patch `pairing.CONFIG_DIR`, `CONFIG_FILE`, `OLD_CONFIG_FILE`. `tools/test_client.py`
moves the REAL cursor and types: manual use only.

## Architecture

- `main.py`: version/system checks → argparse → port (`port_free` with SO_REUSEADDR outside
  Windows, `is_trackpad` = page title check, `next_free_port` up to 20) → `amain`: Pairing,
  backend (`InputBackend` or `DryRunBackend`), volume (`create_volume()` or `FakeVolume`),
  `TrackpadServer`, `poll_volume` task, focus watcher thread → `loop.call_soon_threadsafe`,
  Bonjour `Advertiser.start()` as a background task, banner + QR, `server.run()`.
- `server.py` `TrackpadServer`: websockets `serve(..., process_request=serve_static, max_size=64 KiB,
  ping_interval=20)`; HTTP only for `STATIC_FILES`, WS only on `/ws`. Per connection: `ping` →
  `pong`; `pair`(pin, device) → `paired`(token, name, os) + `focus` + `hover` [+ `volume`] or
  error `bad_pin` / `pairing_locked`; `hello`(token) → same or `bad_token`; anything else before
  auth → `not_authenticated`; after auth `_dispatch`: move dx dy, click button count(1-3),
  down/up button, scroll dx dy (wheel steps, dy>0 up), zoom steps (clamped ±20), text s, key name
  mods, volume level (0-100), mute on. Bad values: printed and ignored.
- `input_backend.py`: sub-pixel remainders (move, macOS scroll at 12 px/step, zoom whole steps);
  macOS double clicks via pynput's private `mouse._click`; zoom = Cmd+= / Cmd+- (mac) or Ctrl+wheel
  (Windows); modifier "cmd" = Cmd on mac, Ctrl on Windows.
- `pairing.py`: 4-digit PIN per run, `MAX_FAILURES` = 10 → `locked` until restart; tokens
  `secrets.token_urlsafe(24)` in `~/.phone-trackpad/config.json` (one-time copy from `~/.phonepad`).
- `focus/`: thread, 0.2 s poll; focus True reported at once, False after 2 readings; hover
  re-checked on cursor move or after 1 s; probe exceptions = no reading.
- `volume.py`: pycaw (Windows), osascript (macOS, slider drags coalesced), FakeVolume.
- `web/app.js`: constants at top (TAP_MS 250, TAP_SLOP 8 px, DRAG_WINDOW_MS 300, LONG_PRESS_MS
  500, AUTO_KEYBOARD_GRACE_MS 900, MAX_SPEED 3); motion batched per animation frame, `sendNow`
  flushes motion before clicks/keys; hidden input with a zero-width sentinel, diffed per `input`.
- Data flow: touch → app.js → WS JSON → `_dispatch` → InputBackend → OS. OS focus → focus thread →
  `set_focus`/`set_hover` → broadcast → app.js opens/closes keyboard.

## Rules and pitfalls

- Keep `pyproject.toml` version == `desktop/version.py` VERSION; Python minimum (3.10) is also in
  both launchers and the CI matrix (`tests/test_project.py` checks all of it). README must list
  every CLI option (also checked).
- `secrets.compare_digest` on `str` raises for non-ASCII: compare bytes.
- Python 3.10 gets websockets 16.1.1 (17 needs 3.11): behaviour can differ by version (16 logs a
  traceback per empty connection; `server._HideEmptyConnections` filters it). CI tests both.
- Don't await slow things before printing the link (Bonjour probing is ~1.2 s).
- Don't read the volume when no phone is connected (osascript ≈ 0.07 s CPU each).
- iOS opens the keyboard only inside a touch handler: keep `maybeOpenKeyboardOnTap()` in `touchend`.
- In tests, never replace `time.monotonic` on the real `time` module (it breaks asyncio timeouts):
  replace the module's reference (`mod.time = ...`). Don't `wait_for(ws.recv())` in probes; use a
  reader task.
- The link is printed ~15 ms before the server listens: tests must wait for the port
  (`AppProcess.wait_ready` does).
- `.bat` must stay CRLF (`.gitattributes`). The launchers' install marker is per platform
  (`.venv/bin/` vs `.venv\Scripts\`) so a folder shared between Windows and macOS works.
- Comments must match the code. Don't add network access or dependencies to the page.

## Verification done for 1.0.0 (macOS, Python 3.13; Python suite also on 3.11)

- Baseline (fde5344, before the cleanup): 142 checks of the first suite pass; the final suite
  on it has 16 failures, all intended changes (pairing lock 5, non-ASCII PIN 3, restart port 1,
  link timing 1, volume polling 1, rename 2, device name 1, Python/system checks 2).
- Behaviour probe old vs new: only index.html, manifest and app.js bytes differ (rename, locked
  message); every input event, reply, log line and page scenario identical. New vs new: 0.
- Link shown: median 1.36 s → 0.14 s (5 runs each). Idle CPU incl. children over ~22 s without a
  phone: median 2.19 s → 0.38 s (3 runs each).
- PIN brute force from the network: paired in 2.5 s before; all 10,000 PINs fail after.
- Package: built twice identically; unzip + launcher + page OK on macOS. Windows and Python
  3.10/3.12/3.14 are covered by CI only.

## Release checklist

1. Bump `pyproject.toml` `version` and `desktop/version.py` `VERSION`.
2. `tests/run_tests.py` → 0 failed; build + `check_package.py` → PROBLEMS: none; probe vs the
   previous tag, explain differences.
3. Commit, push `main`, CI green (10 test jobs + 2 package jobs).
4. `git tag -a vX.Y.Z -m "Phone Trackpad X.Y.Z\n\n- notes"`; `git push origin vX.Y.Z`.
5. CI `release` job: tag == both versions, build, `gh release create` (or update on re-run),
   bot commit of `.github/release-size.json` to main. Check the release page and asset.

## Git setup

- Remote `origin` = https://github.com/mttfntn/phone-trackpad.git (public). Only branch: `main`.
  No CI step creates branches; the only bot push is the badge JSON commit on main.
- Small commits; message says what changed and how it was checked; a bug fix comes before the
  tests that check it. End commit messages with the Co-Authored-By line if an assistant helped.
- Ignored: `.venv/`, `dist/`, `*.zip`, `__pycache__/`, `.DS_Store`, `.claude/`, `.mcp.json`,
  editor folders.
