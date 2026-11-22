"use strict";
// Phone Trackpad phone client: turns touches on this page into mouse/keyboard messages for the desktop helper.

const $ = (id) => document.getElementById(id);
const pad = $("pad"), kbd = $("kbd"), kbBtn = $("kbBtn"), keysBar = $("keys");

const TAP_MS = 250;          // max press length for a tap
const TAP_SLOP = 8;          // max finger travel (px) for a tap
const DRAG_WINDOW_MS = 300;  // tap then touch again within this to start a drag
const SCROLL_PX_PER_STEP = 40;
const MAX_SPEED = 3;
const LONG_PRESS_MS = 500;      // hold this long without moving for a right click
const GESTURE_DECIDE_PX = 10;   // two-finger movement before choosing scroll or pinch
const ZOOM_STEPS_PER_E = 4.3;   // doubling the finger spread is about 3 zoom steps
const AUTO_KEYBOARD_GRACE_MS = 900;  // close a predicted keyboard if no text field got focus by then

// ---------- settings ----------
function load(key, fallback) {
  try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
}
// Clamp so saved values always fit the slider range.
const settings = { speed: Math.min(+load("speed", 0.9) || 0.9, MAX_SPEED), natural: load("natural", true) };

// ---------- connection ----------
let ws = null, authed = false, retryMs = 500, lastPong = 0, computerOS = null;
let pendingPin = null;

const hashPin = new URLSearchParams(location.hash.slice(1)).get("pin");
if (hashPin) {
  pendingPin = hashPin;
  history.replaceState(null, "", location.pathname);  // keep the PIN out of history and bookmarks
}

function deviceName() {
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android phone" : "Phone";
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN && authed) ws.send(JSON.stringify(msg));
}

function setStatus(online, text) {
  $("status").classList.toggle("on", online);
  $("status").setAttribute("aria-label", online ? "Connected" : "Disconnected");
  $("name").textContent = text;
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  authed = false;

  ws.onopen = () => {
    retryMs = 500;
    lastPong = Date.now();
    const token = load("token", null);
    if (pendingPin) {
      ws.send(JSON.stringify({ t: "pair", pin: pendingPin, device: deviceName() }));
      pendingPin = null;
    } else if (token) {
      ws.send(JSON.stringify({ t: "hello", token }));
    } else {
      showPairing(false);
    }
  };

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    switch (msg.t) {
      case "paired":
        authed = true;
        save("token", msg.token);
        computerOS = msg.os;
        $("cmdKey").hidden = msg.os !== "mac";  // on Windows "cmd" would just be Ctrl again
        if ($("pairDlg").open) $("pairDlg").close();
        setStatus(true, msg.name);
        break;
      case "focus":
        onRemoteFocus(msg.editable);
        break;
      case "hover":
        hoverEditable = msg.editable;
        break;
      case "volume":
        onRemoteVolume(msg.level, msg.muted);
        break;
      case "pong":
        lastPong = Date.now();
        break;
      case "error":
        if (msg.msg === "bad_pin") showPairing(true);
        if (msg.msg === "bad_token") { save("token", null); showPairing(false); }
        break;
    }
  };

  ws.onclose = () => {
    authed = false;
    setStatus(false, "Reconnecting");
    hoverEditable = false;
    onRemoteFocus(false);
    setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, 5000);
  };
}

// Keep-alive; a phone that slept often leaves a dead socket that never reports closing.
setInterval(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  if (Date.now() - lastPong > 12000) { ws.close(); return; }
  ws.send('{"t":"ping"}');
}, 5000);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") { retryMs = 500; connect(); }
});

function showPairing(wrong) {
  setStatus(false, "Not paired");
  $("pairErr").hidden = !wrong;
  $("pinInput").value = "";
  if (!$("pairDlg").open) $("pairDlg").showModal();
}

$("pairForm").addEventListener("submit", (e) => {
  const pin = $("pinInput").value.trim();
  if (!/^\d{4}$/.test(pin)) { e.preventDefault(); return; }  // keep the dialog open
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ t: "pair", pin, device: deviceName() }));
  } else {
    pendingPin = pin;
    connect();
  }
});

// ---------- trackpad ----------
const pointers = new Map();  // pointerId -> {x, y}
let gesture = null;          // current touch sequence, reset when all fingers lift
let lastTapEnd = 0, lastTapX = 0, lastTapY = 0;
let moveX = 0, moveY = 0, scrollX = 0, scrollY = 0, zoomSteps = 0, frameQueued = false;

function haptic() { if (navigator.vibrate) navigator.vibrate(8); }

function flushMotion() {
  if (moveX || moveY) {
    send({ t: "move", dx: +moveX.toFixed(2), dy: +moveY.toFixed(2) });
    moveX = moveY = 0;
  }
  if (scrollX || scrollY) {
    send({ t: "scroll", dx: +scrollX.toFixed(3), dy: +scrollY.toFixed(3) });
    scrollX = scrollY = 0;
  }
  if (zoomSteps) {
    send({ t: "zoom", steps: +zoomSteps.toFixed(3) });
    zoomSteps = 0;
  }
}

function queueFrame() {
  if (frameQueued) return;
  frameQueued = true;
  requestAnimationFrame(() => { frameQueued = false; flushMotion(); });
}

// Clicks, presses and keys must land after any motion still waiting for the next frame.
function sendNow(msg) {
  flushMotion();
  send(msg);
}

function accelerate(dx, dy, dtMs) {
  // Faster finger movement moves the cursor proportionally further, like a laptop trackpad.
  const speed = Math.hypot(dx, dy) / Math.max(dtMs, 1);  // px per ms
  const gain = settings.speed * (0.9 + 1.6 * Math.min(speed, 2.5));
  return [dx * gain, dy * gain];
}

pad.addEventListener("pointerdown", (e) => {
  pad.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, t: e.timeStamp });
  pad.classList.add("touching");

  if (!gesture) {
    const now = e.timeStamp;
    const g = gesture = {
      start: now, fingers: 1, travel: 0, dragging: false, longPressed: false,
      // A touch shortly after a tap, near the same spot, becomes a drag once it moves.
      dragArmed: now - lastTapEnd < DRAG_WINDOW_MS && Math.hypot(e.clientX - lastTapX, e.clientY - lastTapY) < 60,
      // Two-finger gestures decide once whether they are a scroll or a pinch.
      mode: null, panX: 0, panY: 0, pinch: 0,
    };
    // Press and hold one finger without moving: right click, like a trackpad's long press.
    if (!g.dragArmed) {
      g.pressTimer = setTimeout(() => {
        if (gesture !== g || g.fingers > 1 || g.travel >= TAP_SLOP) return;
        g.longPressed = true;
        sendNow({ t: "click", button: "right", count: 1 });
        haptic();
      }, LONG_PRESS_MS);
    }
  } else {
    gesture.fingers = Math.max(gesture.fingers, pointers.size);
  }
});

pad.addEventListener("pointermove", (e) => {
  const p = pointers.get(e.pointerId);
  if (!p || !gesture) return;
  const dx = e.clientX - p.x, dy = e.clientY - p.y, dt = e.timeStamp - p.t;
  const oldX = p.x, oldY = p.y;
  p.x = e.clientX; p.y = e.clientY; p.t = e.timeStamp;

  if (gesture.fingers >= 2) {
    if (pointers.size < 2) return;  // one finger of a two-finger gesture lifted early: ignore the rest
    twoFingerMove(e.pointerId, oldX, oldY, dx, dy);
    return;
  }
  if (gesture.longPressed) return;  // the finger is just resting after a right click

  gesture.travel += Math.hypot(dx, dy);
  const [ax, ay] = accelerate(dx, dy, dt);
  if (gesture.dragArmed && !gesture.dragging) {
    // Hold the first few pixels back so the button goes down where the tap was.
    gesture.heldX = (gesture.heldX || 0) + ax;
    gesture.heldY = (gesture.heldY || 0) + ay;
    if (gesture.travel <= TAP_SLOP) return;
    gesture.dragging = true;
    sendNow({ t: "down", button: "left" });
    haptic();
    moveX += gesture.heldX; moveY += gesture.heldY;
  } else {
    moveX += ax; moveY += ay;
  }
  queueFrame();
});

function twoFingerMove(id, oldX, oldY, dx, dy) {
  const g = gesture;
  let other = null;
  for (const [pid, q] of pointers) if (pid !== id) { other = q; break; }
  const before = Math.hypot(oldX - other.x, oldY - other.y);
  const after = Math.hypot(oldX + dx - other.x, oldY + dy - other.y);
  // Only this finger moved, so the midpoint between the two moved by half as much.
  const cx = dx / 2, cy = dy / 2;
  g.travel += Math.hypot(cx, cy);

  if (!g.mode) {
    g.panX += cx; g.panY += cy; g.pinch += after - before;
    const pan = Math.hypot(g.panX, g.panY), pinch = Math.abs(g.pinch);
    if (Math.max(pan, pinch) < GESTURE_DECIDE_PX) return;
    g.mode = pinch > pan ? "zoom" : "scroll";
  }

  if (g.mode === "zoom") {
    if (before > 0 && after > 0) zoomSteps += Math.log(after / before) * ZOOM_STEPS_PER_E;
  } else {
    const sx = cx / SCROLL_PX_PER_STEP, sy = cy / SCROLL_PX_PER_STEP;
    // Wheel convention: dy > 0 scrolls up, dx > 0 scrolls right.
    if (settings.natural) { scrollX -= sx; scrollY += sy; } else { scrollX += sx; scrollY -= sy; }
  }
  queueFrame();
}

function endPointer(e, cancelled) {
  if (!pointers.delete(e.pointerId) || pointers.size > 0 || !gesture) return;
  pad.classList.remove("touching");
  const g = gesture;
  gesture = null;
  clearTimeout(g.pressTimer);
  const quick = e.timeStamp - g.start < TAP_MS && g.travel < TAP_SLOP;

  if (g.longPressed) {
    // Right click already sent while the finger was down.
  } else if (g.dragging) {
    sendNow({ t: "up", button: "left" });
  } else if (!cancelled && quick && g.fingers >= 2) {
    sendNow({ t: "click", button: "right", count: 1 });
    haptic();
  } else if (!cancelled && quick) {
    // Two taps in a row reach the computer as two clicks, which it treats as a double click.
    sendNow({ t: "click", button: "left", count: 1 });
    haptic();
    lastTapEnd = e.timeStamp; lastTapX = e.clientX; lastTapY = e.clientY;
    maybeOpenKeyboardOnTap();
  }
}
pad.addEventListener("pointerup", (e) => endPointer(e, false));
pad.addEventListener("pointercancel", (e) => endPointer(e, true));

// Stops iOS from treating touches on the pad as page gestures and from blurring the keyboard input.
// iOS only opens the keyboard from touch handlers, so taps are also tracked here to focus the input.
let touchTap = null;
pad.addEventListener("touchstart", (e) => {
  e.preventDefault();
  touchTap = e.touches.length === 1 ? { t: e.timeStamp, x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
}, { passive: false });
pad.addEventListener("touchend", (e) => {
  const tap = touchTap;
  touchTap = null;
  if (!tap || e.touches.length) return;
  const end = e.changedTouches[0];
  if (e.timeStamp - tap.t < TAP_MS && Math.hypot(end.clientX - tap.x, end.clientY - tap.y) < TAP_SLOP) {
    maybeOpenKeyboardOnTap();
  }
});
pad.addEventListener("touchmove", (e) => {
  if (touchTap && e.touches.length > 1) touchTap = null;
});
pad.addEventListener("contextmenu", (e) => e.preventDefault());

// ---------- keyboard ----------
// The hidden input always holds a sentinel character so backspace on "empty" is still noticed.
const SENTINEL = "​";
let lastValue = SENTINEL, composing = false, manualKeyboard = false;
let hoverEditable = false;   // the computer says the cursor is over a text field
let remoteEditable = false;  // the computer says a text field has focus
let autoTimer = null;
const mods = new Set();

function resetField() {
  kbd.value = SENTINEL;
  lastValue = SENTINEL;
  try { kbd.setSelectionRange(1, 1); } catch { /* not focused */ }
}
resetField();

function openKeyboard(manual) {
  if (keyboardOpen()) { manualKeyboard = manualKeyboard || manual; return; }
  manualKeyboard = manual;
  resetField();
  kbd.focus();  // only opens the phone keyboard when called from a tap handler
}

function closeKeyboard() {
  manualKeyboard = false;
  clearTimeout(autoTimer);
  kbd.blur();
}

function keyboardOpen() { return document.activeElement === kbd; }

// Called from the tap that clicks on the computer. If that click lands in a text field
// (predicted from hover, or a field already has focus), the keyboard opens on this same tap.
function maybeOpenKeyboardOnTap() {
  if (keyboardOpen() || !(hoverEditable || remoteEditable)) return;
  openKeyboard(false);
  clearTimeout(autoTimer);
  // A wrong guess (the click didn't focus a text field) closes the keyboard again.
  autoTimer = setTimeout(() => { if (!remoteEditable && !manualKeyboard) closeKeyboard(); }, AUTO_KEYBOARD_GRACE_MS);
}

function onRemoteFocus(editable) {
  remoteEditable = editable;
  if (editable) clearTimeout(autoTimer);
  // If the keyboard couldn't open by itself, the icon lights up and the next tap anywhere opens it.
  kbBtn.classList.toggle("hint", editable && !keyboardOpen());
  if (!editable && keyboardOpen() && !manualKeyboard) closeKeyboard();
}

kbBtn.addEventListener("click", () => {
  if (keyboardOpen()) closeKeyboard(); else openKeyboard(true);
});

kbd.addEventListener("focus", () => {
  keysBar.hidden = false;
  kbBtn.classList.remove("hint");
  kbBtn.classList.add("active");
  positionKeysBar();
});
kbd.addEventListener("blur", () => {
  keysBar.hidden = true;
  kbBtn.classList.remove("active");
  kbBtn.classList.toggle("hint", remoteEditable);
  clearMods();
});

kbd.addEventListener("compositionstart", () => { composing = true; });
kbd.addEventListener("compositionend", () => { composing = false; onTyped(); });
kbd.addEventListener("input", onTyped);

// Diff the field against its previous value instead of trusting individual key events:
// this also covers autocorrect replacements and Android keyboards that compose whole words.
function onTyped() {
  const v = kbd.value;
  let p = 0;
  while (p < lastValue.length && p < v.length && lastValue[p] === v[p]) p++;
  const removed = lastValue.length - p;
  const added = v.slice(p);
  for (let i = 0; i < removed; i++) sendNow({ t: "key", name: "backspace", mods: [] });
  if (added) {
    if (mods.size && added.length === 1) {
      sendNow({ t: "key", name: added.toLowerCase(), mods: [...mods] });
      clearMods();
    } else {
      sendNow({ t: "text", s: added });
    }
  }
  lastValue = v;
  if (!composing && (!v.startsWith(SENTINEL) || v.length > 32)) resetField();
}

kbd.addEventListener("keydown", (e) => {
  if (e.isComposing) return;
  if (e.key === "Enter") {
    e.preventDefault();
    sendNow({ t: "key", name: "enter", mods: [...mods] });
    clearMods();
  }
});

function clearMods() {
  mods.clear();
  keysBar.querySelectorAll("[data-mod]").forEach((b) => b.classList.remove("on"));
}

// Special keys act on pointerup; preventing the default on press keeps the input (and keyboard) focused.
keysBar.addEventListener("pointerdown", (e) => { if (e.target.closest("button")) e.preventDefault(); });
keysBar.addEventListener("mousedown", (e) => e.preventDefault());
keysBar.addEventListener("pointerup", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.action === "close") { closeKeyboard(); return; }
  if (b.dataset.mod) {
    const m = b.dataset.mod;
    if (mods.has(m)) mods.delete(m); else mods.add(m);
    b.classList.toggle("on", mods.has(m));
    return;
  }
  sendNow({ t: "key", name: b.dataset.key, mods: [...mods] });
  clearMods();
  haptic();
});

// Keep the special keys bar sitting just above the on-screen keyboard.
function positionKeysBar() {
  const vv = window.visualViewport;
  if (!vv) return;
  const hiddenBelow = window.innerHeight - vv.height - vv.offsetTop;
  keysBar.style.transform = `translateY(${-Math.max(0, hiddenBelow)}px)`;
}
if (window.visualViewport) {
  visualViewport.addEventListener("resize", positionKeysBar);
  visualViewport.addEventListener("scroll", positionKeysBar);
}

// ---------- volume ----------
const volBtn = $("volBtn"), volRow = $("volRow"), volSlider = $("volSlider");
let volMuted = false, volDragging = false, volLastSent = 0, volTimer = null;

function showVolume(level, muted) {
  volMuted = muted;
  volSlider.value = level;
  $("volVal").textContent = level;
  $("spkOn").hidden = muted;
  $("spkOff").hidden = !muted;
}

function onRemoteVolume(level, muted) {
  volBtn.hidden = false;  // only shown once the computer reports it can control volume
  if (!volDragging) showVolume(level, muted);
}

function sendVolume() {
  clearTimeout(volTimer);
  volLastSent = performance.now();
  send({ t: "volume", level: +volSlider.value });
}

volBtn.addEventListener("click", () => {
  volRow.hidden = !volRow.hidden;
  volBtn.classList.toggle("active", !volRow.hidden);
});
$("muteBtn").addEventListener("click", () => {
  showVolume(+volSlider.value, !volMuted);
  send({ t: "mute", on: volMuted });
});
volSlider.addEventListener("pointerdown", () => { volDragging = true; });
volSlider.addEventListener("input", () => {
  volDragging = true;
  $("volVal").textContent = volSlider.value;
  // At most one message per 60 ms while dragging; a trailing send catches the last position.
  const wait = 60 - (performance.now() - volLastSent);
  clearTimeout(volTimer);
  if (wait <= 0) sendVolume(); else volTimer = setTimeout(sendVolume, wait);
});
volSlider.addEventListener("change", () => { sendVolume(); volDragging = false; });
volSlider.addEventListener("pointerup", () => { volDragging = false; });
volSlider.addEventListener("pointercancel", () => { volDragging = false; });

// ---------- settings dialog ----------
$("speed").value = settings.speed;
$("natural").checked = settings.natural;
$("speed").addEventListener("input", (e) => { settings.speed = +e.target.value; save("speed", settings.speed); });
$("natural").addEventListener("change", (e) => { settings.natural = e.target.checked; save("natural", settings.natural); });
$("setBtn").addEventListener("click", () => $("setDlg").showModal());
$("unpair").addEventListener("click", () => {
  save("token", null);
  $("setDlg").close();
  if (ws) ws.close();
});

connect();
