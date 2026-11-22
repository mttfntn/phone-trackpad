# Phone Trackpad

Use your phone (iPhone or Android) as a wireless trackpad and keyboard for a Windows PC or a Mac. Nothing needs to be installed on the phone: the helper running on the computer serves a web page that you open in Safari or Chrome.

- `desktop/`: Python helper. It serves the phone page, receives gestures and injects mouse and keyboard input.
- `desktop/web/`: the phone page (plain HTML/CSS/JS).

## Start

Double-click **`Phone Trackpad.bat`** on Windows or **`Phone Trackpad.command`** on a Mac. You need Python 3 installed ([python.org](https://www.python.org/downloads/)). The first run installs everything Phone Trackpad needs into `desktop/.venv`, which takes a minute; later runs start right away.

On a Mac, the first time, right-click `Phone Trackpad.command` and choose **Open**, because macOS blocks scripts downloaded from the internet. If it says it isn't executable, run `chmod +x "Phone Trackpad.command"` once.

To start it by hand instead:

```
cd desktop
pip install -r requirements.txt
python main.py
```

The helper prints a URL such as `http://192.168.1.21:8765/#pin=1234` and a QR code. Scan it with your phone's camera, or type the URL into the phone's browser. The PIN in the link pairs the phone automatically; after that, `http://192.168.1.21:8765/` is enough.

For a full-screen, app-like experience, add the page to your home screen: **Share → Add to Home Screen** on iPhone, or **⋮ → Add to Home screen** on Android. The home-screen copy pairs separately the first time.

- The phone and the computer must be on the **same Wi-Fi network**.
- Options: `--port 8765`, `--name "My PC"`, `--no-focus`, `-v` (log focus and hover changes). The launchers pass options through, for example `"Phone Trackpad.bat" --name "My PC"`.
- `--dry-run` logs actions instead of controlling the computer. Add `--simulate-focus` so that each click pretends a text field got focus.
- Paired phones are stored in `~/.phone-trackpad/config.json` (phones paired with an older version, when the app was called PhonePad, are carried over from `~/.phonepad`). Delete that file to un-pair every phone, or use Settings → Unpair on the phone.

Test without a phone: open Notepad or TextEdit and put the mouse over it, then, from the repository folder, run `desktop/.venv/bin/python tools/test_client.py <PIN>` (on Windows `desktop\.venv\Scripts\python tools\test_client.py <PIN>`). It moves the real cursor, clicks and types.

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
Tap on a text field on the computer and the phone keyboard opens with that same tap. The helper keeps track of whether the cursor is over a text field, so the phone knows before you tap. If it guesses wrong, the keyboard closes again by itself.

If a text field gets focus some other way (an app focuses it, or the guess missed), the keyboard icon lights up and the next tap anywhere on the pad opens the keyboard. The keyboard icon also opens it by hand at any time.

A bar above the keyboard holds Esc, Tab, arrows, Del and the modifiers. Tap a modifier, then a letter, for shortcuts: for example **Ctrl** then **c**. On a Mac there's also **Cmd**.

## Volume
The speaker icon shows a slider with the computer's current volume, plus mute. Changes made on the computer itself show up on the phone within a second.

## Windows notes
- On first run, allow Python through Windows Firewall on **private** networks. Otherwise the phone can't reach the page.
- Windows won't let the helper control apps running as administrator (Task Manager, installers) unless the helper is also run as administrator.

## macOS notes
- Give **Accessibility** permission to the app that runs the helper (Terminal, iTerm or your Python) in System Settings > Privacy & Security > Accessibility. Without it, clicks, typing and the automatic keyboard won't work.
- The automatic keyboard works best in native apps and Safari. Chromium browsers expose text fields to Accessibility less reliably; use the keyboard icon there.

## Protocol
JSON text frames over WebSocket at `ws://<host>:8765/ws`, each with a `t` field:
`pair`, `hello`, `move`, `click`, `down`, `up`, `scroll`, `zoom`, `text`, `key`, `volume`, `mute` and `ping` go from the phone to the computer; `paired`, `error`, `focus`, `hover`, `volume` and `pong` go back.
See `desktop/server.py` for the fields.
