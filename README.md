# PhonePad

Use your phone (iPhone or Android) as a wireless trackpad and keyboard for a Windows PC or a Mac. Nothing needs to be installed on the phone: the helper running on the computer serves a web page that you open in Safari or Chrome.

- `desktop/`: Python helper. It serves the phone page, receives gestures and injects mouse and keyboard input.
- `desktop/web/`: the phone page (plain HTML/CSS/JS).

## Start

```
cd desktop
pip install -r requirements.txt
python main.py
```

The helper prints a URL such as `http://192.168.1.21:8765/#pin=1234` and a QR code. Scan it with your phone's camera, or type the URL into the phone's browser. The PIN in the link pairs the phone automatically; after that, `http://192.168.1.21:8765/` is enough.

For a full-screen, app-like experience, add the page to your home screen: **Share → Add to Home Screen** on iPhone, or **⋮ → Add to Home screen** on Android. The home-screen copy pairs separately the first time.

- The phone and the computer must be on the **same Wi-Fi network**.
- Options: `--port 8765`, `--name "My PC"`, `--no-focus`, `-v` (log focus changes).
- `--dry-run` logs actions instead of controlling the computer. Add `--simulate-focus` so that each click pretends a text field got focus.
- Paired phones are stored in `~/.phonepad/config.json`. Delete that file to un-pair every phone, or use Settings → Unpair on the phone.

Test without a phone: open Notepad or TextEdit, then run `python test_client.py <PIN>`.

## Gestures
| Gesture | Action |
|---|---|
| One finger drag | Move cursor |
| Tap / two quick taps | Left click / double click |
| Two-finger tap | Right click |
| Two-finger drag | Scroll (natural scrolling can be turned off in Settings) |
| Tap, then touch again and drag | Drag / select |

## Typing
When you click into a text field on the computer, the phone shows a pulsing **Tap to type** button, and one tap opens the phone keyboard. Phone browsers only allow a page to open the keyboard during a tap, so it can't open fully by itself. The keyboard button in the top bar opens it at any time.

A bar above the keyboard holds Esc, Tab, arrows, Del and the modifiers. Tap a modifier, then a letter, for shortcuts: for example **Ctrl** then **c**. On a Mac there's also **Cmd**.

## Windows notes
- On first run, allow Python through Windows Firewall on **private** networks. Otherwise the phone can't reach the page.
- Windows won't let the helper control apps running as administrator (Task Manager, installers) unless the helper is also run as administrator.

## macOS notes
- Give **Accessibility** permission to the app that runs the helper (Terminal, iTerm or your Python) in System Settings > Privacy & Security > Accessibility. Without it, clicks, typing and the Tap to type prompt won't work.
- The Tap to type prompt works best in native apps and Safari. Chromium browsers expose text fields to Accessibility less reliably; use the keyboard button there.

## Protocol
JSON text frames over WebSocket at `ws://<host>:8765/ws`, each with a `t` field:
`pair`, `hello`, `move`, `click`, `down`, `up`, `scroll`, `text`, `key` and `ping` go from the phone to the computer; `paired`, `error`, `focus` and `pong` go back.
See `desktop/server.py` for the fields.
