# Handover: Phone Trackpad

## What it is

Phone Trackpad turns a phone (iPhone or Android) into a wireless trackpad and keyboard for a
Windows PC or a Mac. A Python helper runs on the computer. It serves a web page on the local
network and controls the mouse and keyboard from what the page sends over a WebSocket. Nothing
is installed on the phone: you open the page in Safari or Chrome, optionally from the home
screen.

It is not a fork, and nothing from other projects is bundled: the code, the page and the icon
are original. Third-party libraries are installed from PyPI by the launchers (list below).
Author: Matteo Fontana. Repository: <https://github.com/mttfntn/phone-trackpad> (public).
License: GPL-3.0-or-later. Until November 2026 the project was called PhonePad.

## What you need

- **Python 3.10 to 3.14** (`requires-python = ">=3.10"` in `pyproject.toml`; CI tests all five
  on Windows and macOS). Newer versions aren't blocked.
- **Windows or macOS** for real use. The helper refuses other systems unless `--dry-run`.
- The libraries in `desktop/requirements.txt`, which the launchers install into `desktop/.venv`:

  | Library | Used for | License |
  |---|---|---|
  | pynput | mouse and keyboard input | LGPL-3.0 |
  | websockets (13 or newer: `websockets.asyncio` API) | HTTP page and WebSocket server | BSD-3-Clause |
  | zeroconf (with ifaddr) | Bonjour announcement; ifaddr lists the network addresses | LGPL-2.1-or-later / MIT |
  | qrcode | QR code in the terminal | BSD |
  | pycaw (Windows) | system volume | MIT |
  | uiautomation (Windows) | text-field detection (UI Automation) | Apache-2.0 |
  | pyobjc-framework-ApplicationServices and -Quartz (macOS) | text-field detection (Accessibility API), smooth scrolling | MIT |

- **Node.js 18 or newer** (22 in CI) to run the phone page tests; not needed to use the app.
- `gh` (GitHub CLI) only for release work.

## How the code is organized

| File | What it holds |
|---|---|
| `Phone Trackpad.command`, `Phone Trackpad.bat` | Launchers for macOS and Windows: check Python ≥ 3.10, create `desktop/.venv`, install the requirements when `requirements.txt` changed (marker: `.venv/bin/requirements.installed` or `.venv\Scripts\requirements.installed`), run `main.py` with the given options. |
| `desktop/main.py` | Entry point: Python and system checks, options, port choice (`port_free`, `is_trackpad`, `next_free_port`), `DryRunBackend`, startup banner and QR code, wiring of everything below (`amain`). |
| `desktop/server.py` | `TrackpadServer`: serves the files in `STATIC_FILES` over HTTP and the WebSocket on `/ws` (one port); authentication, message dispatch, focus/hover/volume broadcasts, volume polling. |
| `desktop/input_backend.py` | `InputBackend`: pynput mouse and keyboard; macOS click counts and pixel scrolling through Quartz. |
| `desktop/pairing.py` | `Pairing`: the PIN, the wrong-guess lock, tokens in `~/.phone-trackpad/config.json` (copied once from `~/.phonepad`). |
| `desktop/focus/__init__.py` | `start_focus_watcher`: a thread polling every 0.2 s whether a text field has focus or is under the cursor. |
| `desktop/focus/mac.py`, `desktop/focus/windows.py` | `FocusProbe` for each system (Accessibility API, UI Automation). |
| `desktop/volume.py` | `WindowsVolume` (pycaw), `MacVolume` (osascript), `FakeVolume` (for `--dry-run`), `create_volume`. |
| `desktop/discovery.py` | `local_ipv4_addresses` (for the link) and `Advertiser` (Bonjour announcement `_phone-trackpad._tcp`). |
| `desktop/version.py` | `VERSION` and `MIN_PYTHON`. |
| `desktop/web/` | The phone page: `index.html`, `app.js` (all gesture and keyboard logic), `style.css`, `manifest.webmanifest`, `icon.svg`. |
| `pyproject.toml` | Metadata only (version, Python versions, license); the app isn't pip-installed. |
| `tests/` | Test suite, behaviour probe and package check (see below). |
| `tools/build_package.py` | Builds the release zip. |
| `tools/test_client.py` | Manual check with real input, without a phone. |
| `.github/workflows/ci.yml` | Tests, package check, release on a `v*` tag. |

## How the main feature works

1. **Start.** `main()` checks Python and the system, then the port: `port_free()` binds a test
   socket the way the server will (with `SO_REUSEADDR` outside Windows). If the port is busy,
   `is_trackpad()` asks it for the page: another Phone Trackpad means "already running", anything
   else means the next free port is used. `amain()` builds the parts, starts the Bonjour
   announcement in the background, prints the link `http://<first LAN IPv4>:<port>/#pin=<PIN>`
   and its QR code, and runs the server.
2. **Pairing.** The page reads the PIN from the link (and removes it from the address bar),
   opens `ws://<host>/ws` and sends `pair`. A right PIN gets a random token, saved by the
   helper and in the phone's `localStorage`; later connections send `hello` with the token.
   Ten wrong PINs lock pairing until restart (`Pairing.locked`).
3. **Input.** `app.js` turns pointer events into messages. Motion (`move`, `scroll`, `zoom`) is
   summed and sent once per animation frame; clicks and keys are sent at once, after flushing
   the pending motion. Pointer acceleration, tap/drag/long-press timing and two-finger
   scroll-or-pinch decisions are all in `app.js`. On the helper, `TrackpadServer._dispatch()`
   checks and clamps values and calls `InputBackend`, which keeps sub-pixel remainders.
4. **Typing.** A hidden input on the page holds one invisible sentinel character. Each `input`
   event is diffed against the previous value, giving backspaces plus inserted text, which also
   covers autocorrect and composed words. Modifiers from the keys bar turn the next single
   character into a `key` message.
5. **Keyboard pop-up.** The focus watcher thread reports whether the focused element and the
   element under the cursor accept text. The helper broadcasts `focus` and `hover`. On a tap,
   the page opens the phone keyboard in the same touch handler (iOS only allows it there) if
   `hover` or `focus` is true, and closes it again after 900 ms if no text field got focus.
6. **Volume.** `poll_volume()` reads the system volume once at start, then every second while
   a phone is connected, and broadcasts changes. The phone's slider sends at most one change
   every 60 ms.

## How to make a change

1. Read the module's docstring and this file's "Things to know".
2. Change the code. Keep `app.js` free of dependencies and the helper free of network access
   beyond the local page and Bonjour.
3. Run the tests (next section). For a bug fix, add a check that fails without the fix.
4. Compare behaviour with the previous version (below) and explain every difference.
5. Try it with a real phone for anything in `app.js` or `input_backend.py`.
6. Update the README if users will notice the change.

## How to run the tests

From the repository root, with the Python that has the requirements installed (on a launcher
setup, `desktop/.venv/bin/python`, or `desktop\.venv\Scripts\python` on Windows):

```
python tests/run_tests.py                 # 165 checks (120 Python, 45 page), must end "0 failed"
python tests/run_tests.py --python-only   # without Node.js
python tests/run_tests.py --app-root DIR  # the same tests on another copy of desktop/
```

Nothing touches the real mouse, keyboard, home folder or a running helper. The Python tests use
fakes for pynput, pycaw, uiautomation and pyobjc, so both the Windows and the macOS code run on
either system. End-to-end tests start `main.py --dry-run` with a throwaway home folder. The page
tests run `web/app.js` in Node with a small fake browser (`tests/web/harness.mjs`). Two checks
use the real system and only read: the macOS volume reading (skipped without an audio device)
and the start with the real focus watcher.

**Comparing with the previous version.** Check the old version out into a worktree, probe both,
and compare:

```
git worktree add --detach ../old v1.0.0
python tests/probe_behaviour.py old.json --app-root ../old/desktop
python tests/probe_behaviour.py new.json
python tests/compare_probes.py old.json new.json   # lists every difference
```

The probe records the exact input events for a long list of messages (as Windows and as macOS),
the server's replies, the dry-run log, HTTP answers and 20 gesture scenarios on the page. Two
runs on the same code give 0 differences.

**The package.** `python tools/build_package.py`, then `python tests/check_package.py
dist/phone-trackpad-<version>.zip` unzips it and starts it with this system's launcher, which
installs the requirements from PyPI into a fresh `.venv` (needs internet, about a minute). It
ends with `PROBLEMS: none`.

## How to make a release

1. Set the new version in **both** `pyproject.toml` and `desktop/version.py`
   (`tests/test_project.py` fails if they differ).
2. Run the tests and the package check. Commit, push `main`, wait for green CI.
3. Tag with an annotated message, which becomes the release notes, and push the tag:

   ```
   git tag -a v1.0.1 -m "Phone Trackpad 1.0.1

   - What changed, for users."
   git push origin v1.0.1
   ```

4. CI tests again, checks that the tag matches both version files, builds
   `phone-trackpad-<version>.zip`, publishes the release, and updates
   `.github/release-size.json` on `main` (one bot commit) for the download-size badge. Re-running
   the tag's workflow replaces the zip and notes instead of failing.
5. Check the release page and download the zip once.

## Updating the libraries

No code is bundled from elsewhere. To move to newer libraries, raise the minimums in
`desktop/requirements.txt` only when the code needs it, then run the tests on every supported
Python (CI does). Changing `requirements.txt` makes each user's launcher reinstall on the next
start. `websockets` must stay at 13 or newer (`websockets.asyncio` API).

## Things to know

- **Name change.** Old installs kept tokens in `~/.phonepad/config.json`; `Pairing._load()`
  copies that file once to `~/.phone-trackpad/config.json` when the new one doesn't exist yet.
  The old file is left alone.
- **Port check.** `port_free()` must bind the way asyncio does (`SO_REUSEADDR` outside Windows).
  Without it, a restart right after a phone disconnected looked like a busy port.
- **PIN comparison** uses bytes: `secrets.compare_digest` raises on non-ASCII `str`.
- **Startup order.** The Bonjour announcement takes about 1.2 s (mDNS probing), so it runs in
  the background. Nothing in the project uses it: browsers can't browse Bonjour.
- **macOS volume** goes through `osascript`, about 0.07 s of CPU per reading; hence no polling
  while no phone is connected.
- **macOS input** needs the Accessibility permission for the app that runs the helper. Without
  it, `FocusProbe` prints a warning and input fails silently.
- **iOS keyboard.** The keyboard only opens from a touch handler, so the decision to open it is
  made on the tap itself, using the `hover` state that arrived before.
- **Dates and timers in `app.js`** use `e.timeStamp`, `performance.now()` and `Date.now()`; the
  test harness drives all of them from one fake clock. Keep new timing code on these.
- **Line endings.** `.gitattributes` keeps `.bat` files CRLF (cmd needs it) and everything else
  LF. A copy of the folder that went through Windows may have CRLF Python files, which is
  harmless.
- Local setups (`desktop/.venv`, `.claude/`, `.mcp.json`, editor folders) are git-ignored.

## Known limits

- Windows and macOS only; same local network only.
- Plain HTTP: traffic on the local network isn't encrypted (see README, Security). HTTPS would
  need a certificate the phone trusts, for a local IP address.
- Text-field detection depends on each app's accessibility support (weak in Chromium browsers
  on the Mac).
- Apps running as administrator on Windows can't be controlled unless the helper is too.
- On macOS, the focus watcher's CPU cost with Accessibility granted hasn't been measured (the
  test runs had no permission).
- A home-screen copy of the page has its own storage, so it pairs separately.
