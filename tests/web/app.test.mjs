// Phone page (web/app.js): pairing, gestures, typing, the keys bar, volume and settings.
// Run with: node --test tests/web/
import test from "node:test";
import assert from "node:assert/strict";
import { Page } from "./harness.mjs";

const paired = (opts = {}) => {
  const p = new Page({ storage: { token: JSON.stringify("tok123") }, ...opts });
  p.connect(opts);
  return p;
};
const sum = (msgs, k) => msgs.reduce((a, m) => a + m[k], 0);

// ---------- connection and pairing ----------

test("connects to /ws on the same host", () => {
  const p = new Page();
  assert.equal(p.ws.url, "ws://192.168.1.15:8765/ws");
});

test("PIN in the link pairs, then is removed from the address", () => {
  const p = new Page({ hash: "#pin=1234" });
  assert.equal(p.historyCalls.length, 1);
  p.ws.serverOpen();
  assert.deepEqual(p.ws.sent[0], { t: "pair", pin: "1234", device: "iPhone" });
  p.ws.serverSend({ t: "paired", token: "newtok", name: "PC", os: "windows" });
  assert.equal(p.storage.token, JSON.stringify("newtok"));
  assert.equal(p.el("name").textContent, "PC");
  assert.ok(p.el("status").classList.contains("on"));
  assert.equal(p.el("cmdKey").hidden, true, "no Cmd key for Windows");
});

test("saved token says hello; Mac shows the Cmd key", () => {
  const p = new Page({ storage: { token: JSON.stringify("tok123") } });
  const first = p.connect({ os: "mac" });
  assert.deepEqual(first, { t: "hello", token: "tok123" });
  assert.equal(p.el("cmdKey").hidden, false);
});

test("no token: pairing dialog, wrong PIN shows the error", () => {
  const p = new Page();
  p.ws.serverOpen();
  assert.equal(p.el("pairDlg").open, true);
  assert.equal(p.el("pairErr").hidden, true);
  p.el("pinInput").value = "12a4";
  const bad = p.el("pairForm").dispatch("submit");
  assert.equal(bad.defaultPrevented, true);
  assert.equal(p.ws.sent.length, 0);
  p.el("pinInput").value = " 4321 ";
  p.el("pairForm").dispatch("submit");
  assert.deepEqual(p.ws.sent.at(-1), { t: "pair", pin: "4321", device: "iPhone" });
  p.ws.serverSend({ t: "error", msg: "bad_pin" });
  assert.equal(p.el("pairErr").hidden, false);
  assert.equal(p.el("pinInput").value, "");
});

test("locked pairing explains what to do", () => {
  const p = new Page();
  p.ws.serverOpen();
  p.ws.serverSend({ t: "error", msg: "bad_pin" });
  assert.equal(p.el("pairErr").textContent, "Wrong PIN");
  p.ws.serverSend({ t: "error", msg: "pairing_locked" });
  assert.equal(p.el("pairErr").hidden, false);
  assert.match(p.el("pairErr").textContent, /Restart Phone Trackpad/);
  p.ws.serverSend({ t: "error", msg: "bad_pin" });
  assert.equal(p.el("pairErr").textContent, "Wrong PIN");
});

test("bad token forgets it and asks for the PIN", () => {
  const p = new Page({ storage: { token: JSON.stringify("old") } });
  p.ws.serverOpen();
  p.ws.serverSend({ t: "error", msg: "bad_token" });
  assert.equal(p.storage.token, "null");
  assert.equal(p.el("pairDlg").open, true);
});

test("device names", () => {
  for (const [ua, name] of [["(iPad; CPU OS)", "iPad"], ["Linux; Android 14", "Android phone"], ["Other", "Phone"]]) {
    const p = new Page({ hash: "#pin=1111", userAgent: ua });
    p.ws.serverOpen();
    assert.equal(p.ws.sent[0].device, name);
  }
});

test("nothing is sent before pairing", () => {
  const p = new Page();
  p.ws.serverOpen();
  p.tap();
  p.drag([[10, 0]]);
  assert.deepEqual(p.ws.sent, []);
});

test("reconnects with growing delay, capped at 5 s", () => {
  const p = paired();
  const delays = [];
  for (let i = 0; i < 6; i++) {
    const before = p.sockets.length;
    p.ws.close();
    let waited = 0;
    while (p.sockets.length === before) { p.advance(50); waited += 50; }
    delays.push(waited);
  }
  assert.deepEqual(delays, [500, 1000, 2000, 4000, 5000, 5000]);
  assert.equal(p.el("name").textContent, "Reconnecting");
});

test("keep-alive pings, and closes a socket whose pongs stopped", () => {
  const p = paired();
  p.advance(5000);
  assert.deepEqual(p.ws.sent.at(-1), { t: "ping" });
  p.advance(10000);  // 15 s without a pong
  assert.equal(p.ws.readyState, 3);
});

// ---------- trackpad ----------

test("tap clicks once, with a haptic tick", () => {
  const p = paired();
  p.tap();
  assert.deepEqual(p.msgs(), [{ t: "click", button: "left", count: 1 }]);
  assert.equal(p.vibrations, 1);
});

test("slow press is not a tap", () => {
  const p = paired();
  p.tap(100, 100, 300);
  assert.deepEqual(p.msgs(), []);
});

test("two quick taps are two clicks", () => {
  const p = paired();
  p.tap();
  p.advance(100);
  p.tap();
  assert.equal(p.msgs("click").length, 2);
  assert.equal(p.msgs("down").length, 0);
});

test("moves are accelerated, batched per frame, and scaled by speed", () => {
  const p = paired();
  p.drag([[2, 0], [2, 0]], { stepMs: 16 });    // slow
  const slow = sum(p.msgs("move"), "dx");
  p.sent.length = 0;
  p.drag([[20, 0], [20, 0]], { stepMs: 16 });  // fast
  const fast = sum(p.msgs("move"), "dx");
  assert.ok(slow > 3 && slow < 6, `slow ${slow}`);
  assert.ok(fast / 40 > slow / 4 * 1.5, "faster finger moves the cursor further per pixel");
  assert.ok(p.msgs("move").length <= 2, "one message per frame");
});

test("pointer speed setting scales movement and is saved", () => {
  const p = paired();
  p.el("speed").value = "2";
  p.el("speed").dispatch("input", { target: p.el("speed") });
  assert.equal(p.storage.speed, "2");
  p.drag([[4, 0]]);
  const fast = sum(p.msgs("move"), "dx");
  const q = paired();
  q.drag([[4, 0]]);
  assert.ok(Math.abs(fast / sum(q.msgs("move"), "dx") - 2 / 0.9) < 0.01);
});

test("saved speed is clamped to the slider maximum", () => {
  const p = new Page({ storage: { speed: "9" } });
  assert.equal(p.el("speed").value, 3);
  const q = new Page({ storage: { speed: "\"junk\"" } });
  assert.equal(q.el("speed").value, 0.9);
});

test("tap then touch again and move drags", () => {
  const p = paired();
  p.tap(100, 100);
  p.advance(100);
  p.drag([[3, 0], [3, 0], [3, 0], [10, 0]], { x: 100, y: 100 });
  const kinds = p.msgs().map((m) => m.t);
  assert.deepEqual(kinds.slice(0, 2), ["click", "down"]);
  assert.equal(kinds.at(-1), "up");
  assert.ok(kinds.includes("move"));
  // The held-back first pixels are sent after the button goes down.
  assert.ok(kinds.indexOf("move") > kinds.indexOf("down"));
});

test("touch after the drag window is a plain move", () => {
  const p = paired();
  p.tap();
  p.advance(400);
  p.drag([[10, 0], [10, 0]]);
  assert.equal(p.msgs("down").length, 0);
});

test("press and hold right-clicks once; the following movement is ignored", () => {
  const p = paired();
  p.pointer("pointerdown", 1, 100, 100);
  p.advance(499);
  assert.equal(p.msgs("click").length, 0);
  p.advance(1);
  assert.deepEqual(p.msgs("click"), [{ t: "click", button: "right", count: 1 }]);
  p.pointer("pointermove", 1, 150, 100);
  p.frame();
  p.advance(100);
  p.pointer("pointerup", 1, 150, 100);
  assert.deepEqual(p.msgs().map((m) => m.t), ["click"]);
});

test("hold after moving is not a right click", () => {
  const p = paired();
  p.drag([[20, 0]], { lift: false });
  p.advance(600);
  assert.equal(p.msgs("click").length, 0);
});

test("two-finger tap right-clicks", () => {
  const p = paired();
  p.pointer("pointerdown", 1, 100, 100);
  p.pointer("pointerdown", 2, 150, 100);
  p.advance(80);
  p.pointer("pointerup", 2, 150, 100);
  p.pointer("pointerup", 1, 100, 100);
  assert.deepEqual(p.msgs(), [{ t: "click", button: "right", count: 1 }]);
});

function twoFingerScroll(p, dy) {
  p.pointer("pointerdown", 1, 100, 100);
  p.pointer("pointerdown", 2, 150, 100);
  for (let i = 0; i < 10; i++) {
    p.advance(16);
    p.pointer("pointermove", 1, 100, 100 + dy * (i + 1));
    p.pointer("pointermove", 2, 150, 100 + dy * (i + 1));
    p.frame();
  }
  p.pointer("pointerup", 1, 100, 100 + dy * 10);
  p.pointer("pointerup", 2, 150, 100 + dy * 10);
}

test("two-finger drag scrolls; natural scrolling flips direction", () => {
  const p = paired();
  twoFingerScroll(p, 8);  // fingers move down
  const natural = sum(p.msgs("scroll"), "dy");
  // 20 finger moves of 8 px move the midpoint 80 px; the first 8 px only decide the gesture.
  assert.ok(Math.abs(natural - (80 - 8) / 40) < 0.01, `natural ${natural}`);
  assert.equal(p.msgs("zoom").length, 0);
  assert.equal(p.msgs("click").length, 0);

  const q = paired();
  q.el("natural").dispatch("change", { target: { checked: false } });
  assert.equal(q.storage.natural, "false");
  twoFingerScroll(q, 8);
  assert.ok(Math.abs(sum(q.msgs("scroll"), "dy") + natural) < 0.01);
});

test("pinch out zooms in, pinch in zooms out", () => {
  const p = paired();
  p.pointer("pointerdown", 1, 100, 100);
  p.pointer("pointerdown", 2, 200, 100);
  for (let i = 1; i <= 10; i++) {   // spread doubles: 100 -> 200 px
    p.advance(16);
    p.pointer("pointermove", 2, 200 + 10 * i, 100);
    p.frame();
  }
  p.pointer("pointerup", 2, 300, 100);
  p.pointer("pointerup", 1, 100, 100);
  const zin = sum(p.msgs("zoom"), "steps");
  // About 3 steps for a doubling (minus the first 10 px used to decide).
  assert.ok(zin > 2.4 && zin < 3.1, `zoom ${zin}`);
  assert.equal(p.msgs("scroll").length, 0);
});

test("clicks are sent after pending movement", () => {
  const p = paired();
  p.pointer("pointerdown", 1, 100, 100);
  p.advance(16);
  p.pointer("pointermove", 1, 101, 100);  // within tap slop, no frame yet
  p.advance(16);
  p.pointer("pointerup", 1, 101, 100);
  assert.deepEqual(p.msgs().map((m) => m.t), ["move", "click"]);
});

test("cancelled touch does not click", () => {
  const p = paired();
  p.pointer("pointerdown", 1, 100, 100);
  p.advance(50);
  p.pointer("pointercancel", 1, 100, 100);
  assert.deepEqual(p.msgs(), []);
});

test("pad blocks page gestures and the context menu", () => {
  const p = paired();
  assert.equal(p.touch("touchstart", [[1, 1]]).defaultPrevented, true);
  assert.equal(p.el("pad").dispatch("contextmenu").defaultPrevented, true);
});

// ---------- keyboard ----------

test("keyboard button opens and closes the keyboard and the keys bar", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  assert.equal(p.document.activeElement, p.el("kbd"));
  assert.equal(p.el("keys").hidden, false);
  assert.ok(p.el("kbBtn").classList.contains("active"));
  p.el("kbBtn").dispatch("click");
  assert.equal(p.document.activeElement, null);
  assert.equal(p.el("keys").hidden, true);
});

test("typing sends text, deletions send backspaces", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  const S = p.el("kbd").value;   // sentinel character
  assert.equal(S.length, 1);
  p.type(S + "h");
  p.type(S + "hé");
  p.type(S + "h");
  p.type(S);
  p.type("");                     // backspace on the sentinel itself
  assert.deepEqual(p.msgs(), [
    { t: "text", s: "h" }, { t: "text", s: "é" },
    { t: "key", name: "backspace", mods: [] },
    { t: "key", name: "backspace", mods: [] },
    { t: "key", name: "backspace", mods: [] },
  ]);
  assert.equal(p.el("kbd").value, S, "field reset after the sentinel was deleted");
});

test("autocorrect replacement is a diff", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  const S = p.el("kbd").value;
  p.type(S + "teh");
  p.sent.length = 0;
  p.type(S + "the ");
  assert.deepEqual(p.msgs(), [
    { t: "key", name: "backspace", mods: [] }, { t: "key", name: "backspace", mods: [] },
    { t: "text", s: "he " },
  ]);
});

test("composition is sent when it ends", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  const S = p.el("kbd").value;
  p.el("kbd").dispatch("compositionstart");
  p.type(S + "に");
  p.el("kbd").dispatch("compositionend");
  assert.deepEqual(p.msgs("text")[0], { t: "text", s: "に" });
});

test("long text field is reset so it never grows", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  const S = p.el("kbd").value;
  p.type(S + "x".repeat(40));
  assert.equal(p.el("kbd").value, S);
});

test("Enter sends the enter key with modifiers", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  p.el("keys").dispatch("pointerup", { target: p.key({ mod: "shift" }) });
  const ev = p.el("kbd").dispatch("keydown", { key: "Enter", isComposing: false });
  assert.equal(ev.defaultPrevented, true);
  assert.deepEqual(p.msgs(), [{ t: "key", name: "enter", mods: ["shift"] }]);
  p.el("kbd").dispatch("keydown", { key: "Enter", isComposing: true });
  assert.equal(p.msgs().length, 1);
});

test("modifier then letter sends a shortcut and clears the modifier", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  const ctrl = p.key({ mod: "ctrl" }), cmd = p.key({ mod: "cmd" });
  const bar = p.el("keys");
  bar.dispatch("pointerup", { target: ctrl });
  bar.dispatch("pointerup", { target: cmd });
  assert.ok(ctrl.classList.contains("on"));
  const S = p.el("kbd").value;
  p.type(S + "C");
  assert.deepEqual(p.msgs(), [{ t: "key", name: "c", mods: ["ctrl", "cmd"] }]);
  assert.ok(!ctrl.classList.contains("on"));
  p.type(S + "Cd");
  assert.deepEqual(p.msgs().at(-1), { t: "text", s: "d" });
});

test("tapping a modifier twice turns it off", () => {
  const p = paired();
  const bar = p.el("keys"), alt = p.key({ mod: "alt" });
  bar.dispatch("pointerup", { target: alt });
  bar.dispatch("pointerup", { target: alt });
  bar.dispatch("pointerup", { target: p.key({ key: "tab" }) });
  assert.deepEqual(p.msgs(), [{ t: "key", name: "tab", mods: [] }]);
});

test("special keys bar sends keys and keeps the keyboard focused", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  const bar = p.el("keys");
  for (const k of ["esc", "tab", "left", "up", "down", "right", "delete"]) {
    const b = p.key({ key: k });
    assert.equal(bar.dispatch("pointerdown", { target: b }).defaultPrevented, true);
    bar.dispatch("pointerup", { target: b });
  }
  assert.deepEqual(p.msgs().map((m) => m.name), ["esc", "tab", "left", "up", "down", "right", "delete"]);
  bar.dispatch("pointerup", { target: p.key({ action: "close" }) });
  assert.equal(p.document.activeElement, null);
  // Releases outside a button do nothing.
  bar.dispatch("pointerup", { target: bar });
  assert.equal(p.msgs().length, 7);
});

test("keyboard opens on the tap that clicks a text field", () => {
  const p = paired();
  p.ws.serverSend({ t: "hover", editable: true });
  p.tap();
  assert.equal(p.document.activeElement, p.el("kbd"));
  p.ws.serverSend({ t: "focus", editable: true });
  p.advance(1000);
  assert.equal(p.document.activeElement, p.el("kbd"), "stays open: a field got focus");
});

test("wrong guess closes the keyboard again after 900 ms", () => {
  const p = paired();
  p.ws.serverSend({ t: "hover", editable: true });
  p.tap();
  assert.equal(p.document.activeElement, p.el("kbd"));
  p.advance(899);
  assert.equal(p.document.activeElement, p.el("kbd"));
  p.advance(1);
  assert.equal(p.document.activeElement, null);
});

test("no text field under the cursor: tap does not open the keyboard", () => {
  const p = paired();
  p.tap();
  assert.equal(p.document.activeElement, null);
});

test("focus elsewhere lights the keyboard icon; focus lost closes an auto-opened keyboard", () => {
  const p = paired();
  p.ws.serverSend({ t: "focus", editable: true });
  assert.ok(p.el("kbBtn").classList.contains("hint"));
  p.tap();
  assert.equal(p.document.activeElement, p.el("kbd"));
  p.ws.serverSend({ t: "focus", editable: false });
  assert.equal(p.document.activeElement, null);
});

test("a keyboard opened by hand stays open when focus is lost", () => {
  const p = paired();
  p.el("kbBtn").dispatch("click");
  p.ws.serverSend({ t: "focus", editable: true });
  p.ws.serverSend({ t: "focus", editable: false });
  assert.equal(p.document.activeElement, p.el("kbd"));
});

test("disconnect closes an auto-opened keyboard", () => {
  const p = paired();
  p.ws.serverSend({ t: "focus", editable: true });
  p.tap();
  p.ws.close();
  assert.equal(p.document.activeElement, null);
});

// ---------- volume ----------

test("volume button appears once the computer reports volume", () => {
  const p = paired();
  assert.equal(p.el("volBtn").hidden, true);
  p.ws.serverSend({ t: "volume", level: 35, muted: true });
  assert.equal(p.el("volBtn").hidden, false);
  assert.equal(p.el("volSlider").value, 35);
  assert.equal(p.el("volVal").textContent, 35);
  assert.equal(p.el("spkOff").hidden, false);
  p.el("volBtn").dispatch("click");
  assert.equal(p.el("volRow").hidden, false);
});

test("slider drag sends at most every 60 ms and the final value", () => {
  const p = paired();
  p.ws.serverSend({ t: "volume", level: 50, muted: false });
  const s = p.el("volSlider");
  s.dispatch("pointerdown");
  for (let v = 51; v <= 60; v++) {
    s.value = String(v);
    s.dispatch("input");
    p.advance(10);
  }
  p.ws.serverSend({ t: "volume", level: 10, muted: false });  // ignored while dragging
  assert.equal(s.value, "60");
  s.dispatch("change");
  s.dispatch("pointerup");
  const levels = p.msgs("volume").map((m) => m.level);
  assert.ok(levels.length >= 2 && levels.length <= 4, `${levels}`);
  assert.equal(levels.at(-1), 60);
});

test("mute button toggles", () => {
  const p = paired();
  p.ws.serverSend({ t: "volume", level: 50, muted: false });
  p.el("muteBtn").dispatch("click");
  p.el("muteBtn").dispatch("click");
  assert.deepEqual(p.msgs("mute"), [{ t: "mute", on: true }, { t: "mute", on: false }]);
});

// ---------- settings ----------

test("unpair forgets the token and disconnects", () => {
  const p = paired();
  p.el("setBtn").dispatch("click");
  assert.equal(p.el("setDlg").open, true);
  p.el("unpair").dispatch("click");
  assert.equal(p.storage.token, "null");
  assert.equal(p.el("setDlg").open, false);
  assert.equal(p.sockets[0].readyState, 3);
});
