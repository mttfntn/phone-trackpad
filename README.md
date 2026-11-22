# Phone Trackpad

[![Python](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmttfntn%2Fphone-trackpad%2Fmain%2Fpyproject.toml&query=%24.project%5B%27requires-python%27%5D&label=Python&color=3776AB&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-555)](#start)
[![Release](https://img.shields.io/github/v/release/mttfntn/phone-trackpad)](https://github.com/mttfntn/phone-trackpad/releases/latest)
[![Download size](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmttfntn%2Fphone-trackpad%2Fmain%2F.github%2Frelease-size.json)](https://github.com/mttfntn/phone-trackpad/releases/latest)
[![Tests](https://github.com/mttfntn/phone-trackpad/actions/workflows/ci.yml/badge.svg)](https://github.com/mttfntn/phone-trackpad/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/mttfntn/phone-trackpad)](LICENSE)
[![Language](https://img.shields.io/github/languages/top/mttfntn/phone-trackpad)](desktop/main.py)

Use your phone (iPhone or Android) as a wireless trackpad and keyboard for a Windows PC or a
Mac. Nothing needs to be installed on the phone: a small helper running on the computer serves
a web page that you open in Safari or Chrome.

- `desktop/`: the Python helper. It serves the phone page, receives gestures and injects mouse
  and keyboard input.
- `desktop/web/`: the phone page (plain HTML, CSS and JavaScript).

For maintainers: [HANDOVER.md](HANDOVER.md) (people) and [AGENTS.md](AGENTS.md) (AI assistants).

## Start

Download `phone-trackpad-<version>.zip` from the
[latest release](https://github.com/mttfntn/phone-trackpad/releases/latest) and unzip it.
Double-click **`Phone Trackpad.bat`** on Windows or **`Phone Trackpad.command`** on a Mac.
You need Python 3.10 or newer ([python.org](https://www.python.org/downloads/)). The first run
installs everything Phone Trackpad needs into `desktop/.venv`, which takes a minute; later runs
start right away.

On a Mac, the first time, right-click `Phone Trackpad.command` and choose **Open**, because
macOS blocks scripts downloaded from the internet. If it says it isn't executable, run
`chmod +x "Phone Trackpad.command"` once.

To start it by hand instead:

```
cd desktop
pip install -r requirements.txt
python main.py
```

The helper prints a link such as `http://192.168.1.21:8765/#pin=1234` and a QR code. Scan it
with your phone's camera, or type the link into the phone's browser. The PIN in the link pairs
the phone automatically; after that, `http://192.168.1.21:8765/` is enough. Keep the helper's
window open while you use the phone; closing it stops Phone Trackpad.

For a full-screen, app-like experience, add the page to your home screen: **Share → Add to Home
Screen** on iPhone, or **⋮ → Add to Home screen** on Android. The home-screen copy pairs
separately the first time.

- The phone and the computer must be on the **same Wi-Fi network**.
- Paired phones are stored in `~/.phone-trackpad/config.json`. Delete that file to un-pair every
  phone, or use Settings → Unpair on the phone. Phones paired with an older version (when the
  app was called PhonePad) are carried over from `~/.phonepad` on the first start.

## Options

The launchers pass options through, for example `"Phone Trackpad.bat" --name "My PC"`.

| Option | What it does |
|---|---|
| `--port 8765` | Port for the page. If another program already uses it, Phone Trackpad takes the next free port and says so; the printed link has the new port. |
| `--name "My PC"` | Name shown on the phone (default: the computer's name). |
| `--no-focus` | Don't watch for text fields, so the keyboard never opens by itself. |
| `-v` / `--verbose` | Log focus and hover changes. |
| `--dry-run` | Log actions instead of controlling the computer. |
| `--simulate-focus` | With `--dry-run`: each click pretends a text field got focus. |

## Gestures

| Gesture | Action |
|---|---|
| One finger drag | Move cursor |
| Tap / two quick taps | Left click / double click |
| Press and hold (half a second) | Right click |
| Two-finger tap | Right click |
| Two-finger drag | Scroll (natural scrolling can be turned off in Settings) |
| Pinch out / in | Zoom in / out (Ctrl+wheel on Windows, Cmd+= / Cmd+- on Mac) |
| Tap, then touch again and drag | Drag / select |

Pointer speed is in Settings (the sliders icon).

## Typing

Tap on a text field on the computer and the phone keyboard opens with that same tap. The helper
keeps track of whether the cursor is over a text field, so the phone knows before you tap. If it
guesses wrong, the keyboard closes again by itself.

If a text field gets focus some other way (an app focuses it, or the guess missed), the keyboard
icon lights up and the next tap anywhere on the pad opens the keyboard. The keyboard icon also
opens it by hand at any time.

A bar above the keyboard holds Esc, Tab, arrows, Del and the modifiers. Tap a modifier, then a
letter, for shortcuts: for example **Ctrl** then **c**. On a Mac there's also **Cmd**.

## Volume

The speaker icon shows a slider with the computer's current volume, plus mute. Changes made on
the computer itself show up on the phone within about a second.

## Windows notes

- On first run, allow Python through Windows Firewall on **private** networks. Otherwise the
  phone can't reach the page.
- Windows won't let the helper control apps running as administrator (Task Manager, installers)
  unless the helper is also run as administrator.

## macOS notes

- Give **Accessibility** permission to the app that runs the helper (Terminal, iTerm or your
  Python) in System Settings › Privacy & Security › Accessibility. Without it, clicks, typing
  and the automatic keyboard won't work.
- The automatic keyboard works best in native apps and Safari. Chromium browsers expose text
  fields to Accessibility less reliably; use the keyboard icon there.

## Security

- Pairing needs the 4-digit PIN that the helper prints, which changes every time it starts.
  After 10 wrong PINs, pairing new phones is switched off until you restart the helper; phones
  that are already paired keep working.
- The page and the WebSocket use plain HTTP on your local network, so they aren't encrypted.
  Someone who can watch your Wi-Fi traffic could see what you type and copy a phone's pairing
  token. Use Phone Trackpad on networks you trust, and close it when you're done.
- To report a security problem, see [SECURITY.md](SECURITY.md).

## Known limits

- Windows and macOS only. On other systems the helper only runs with `--dry-run`.
- Phone and computer must be on the same local network; there's no relay over the internet.
- The automatic keyboard depends on what each app reports to Windows UI Automation or the macOS
  Accessibility API; some apps (Chromium browsers on the Mac, games, remote desktops) report
  text fields unreliably or not at all. The keyboard icon always works.
- Apps running as administrator on Windows can't be controlled unless the helper is too.
- Each copy of the page added to the home screen pairs separately.

## Test without a phone

Open Notepad or TextEdit and put the mouse over it, then, from the repository folder, run
`desktop/.venv/bin/python tools/test_client.py <PIN>` (on Windows
`desktop\.venv\Scripts\python tools\test_client.py <PIN>`). It moves the real cursor, clicks
and types. The automated tests are described in [HANDOVER.md](HANDOVER.md#how-to-run-the-tests).

## Protocol

JSON text frames over WebSocket at `ws://<host>:8765/ws`, each with a `t` field:
`pair`, `hello`, `move`, `click`, `down`, `up`, `scroll`, `zoom`, `text`, `key`, `volume`,
`mute` and `ping` go from the phone to the computer; `paired`, `error` (`bad_pin`,
`pairing_locked`, `bad_token`, `not_authenticated`), `focus`, `hover`, `volume` and `pong` go
back. See `desktop/server.py` for the fields.

## License

[GPL-3.0-or-later](LICENSE). © Matteo Fontana.
