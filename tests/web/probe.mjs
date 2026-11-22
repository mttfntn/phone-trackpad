// Prints (as JSON) every message the phone page sends for a fixed set of scripted gestures,
// so two versions of web/app.js can be compared (see tests/probe_behaviour.py).
import { Page } from "./harness.mjs";

const out = {};
const run = (name, fn, opts) => {
  const p = new Page({ storage: { token: JSON.stringify("tok") }, ...opts });
  p.connect({ os: "mac" });
  fn(p);
  out[name] = { sent: p.sent, vibrations: p.vibrations, keyboard: p.document.activeElement === p.el("kbd"),
    storage: p.storage };
};

for (const speed of [0.2, 0.9, 3]) {
  for (const stepMs of [4, 16, 50]) {
    run(`move speed ${speed} step ${stepMs}`, (p) => {
      p.el("speed").dispatch("input", { target: { value: String(speed) } });
      p.drag([[1, 0], [3, 2], [7, -4], [15, 9], [30, 0], [-12, 5], [0.5, 0.5]], { stepMs });
    });
  }
}
run("taps", (p) => { p.tap(); p.advance(120); p.tap(); p.advance(500); p.tap(10, 10, 240); p.tap(10, 10, 260); });
run("tap-drag", (p) => {
  p.tap(50, 50);
  p.advance(150);
  p.drag([[2, 0], [2, 1], [5, 5], [20, 0]], { x: 52, y: 50 });
});
run("long press", (p) => { p.pointer("pointerdown", 1, 5, 5); p.advance(700); p.pointer("pointerup", 1, 5, 5); });
run("two-finger tap", (p) => {
  p.pointer("pointerdown", 1, 0, 0); p.pointer("pointerdown", 2, 40, 0); p.advance(100);
  p.pointer("pointerup", 1, 0, 0); p.pointer("pointerup", 2, 40, 0);
});
for (const natural of [true, false]) {
  run(`scroll natural ${natural}`, (p) => {
    p.el("natural").dispatch("change", { target: { checked: natural } });
    p.pointer("pointerdown", 1, 100, 100); p.pointer("pointerdown", 2, 160, 100);
    for (let i = 1; i <= 15; i++) {
      p.advance(16);
      p.pointer("pointermove", 1, 100 + i * 2, 100 + i * 7);
      p.pointer("pointermove", 2, 160 + i * 2, 100 + i * 7);
      p.frame();
    }
    p.pointer("pointerup", 1, 0, 0); p.pointer("pointerup", 2, 0, 0);
  });
}
run("pinch in and out", (p) => {
  p.pointer("pointerdown", 1, 100, 100); p.pointer("pointerdown", 2, 300, 100);
  for (let i = 1; i <= 10; i++) { p.advance(16); p.pointer("pointermove", 2, 300 - i * 10, 100); p.frame(); }
  for (let i = 1; i <= 20; i++) { p.advance(16); p.pointer("pointermove", 1, 100 - i * 5, 100); p.frame(); }
  p.pointer("pointerup", 1, 0, 0); p.pointer("pointerup", 2, 0, 0);
});
run("typing", (p) => {
  p.el("kbBtn").dispatch("click");
  const S = p.el("kbd").value;
  for (const v of [S + "a", S + "ab", S + "abc", S + "ab", S + "abd e", S, "", S + "x".repeat(33)]) p.type(v);
  p.el("kbd").dispatch("compositionstart"); p.type(S + "か"); p.type(S + "かな"); p.el("kbd").dispatch("compositionend");
  p.el("keys").dispatch("pointerup", { target: p.key({ mod: "cmd" }) });
  p.el("keys").dispatch("pointerup", { target: p.key({ mod: "shift" }) });
  p.type(S + "かなZ");
  p.el("kbd").dispatch("keydown", { key: "Enter" });
  for (const k of ["esc", "tab", "left", "up", "down", "right", "delete"]) {
    p.el("keys").dispatch("pointerup", { target: p.key({ key: k }) });
  }
});
run("keyboard prediction", (p) => {
  p.ws.serverSend({ t: "hover", editable: true });
  p.tap();
  p.advance(1000);
  p.ws.serverSend({ t: "focus", editable: true });
  p.tap();
  p.ws.serverSend({ t: "focus", editable: false });
});
run("volume", (p) => {
  p.ws.serverSend({ t: "volume", level: 40, muted: false });
  const s = p.el("volSlider");
  s.dispatch("pointerdown");
  for (let v = 41; v <= 70; v += 3) { s.value = String(v); s.dispatch("input"); p.advance(25); }
  s.dispatch("change"); s.dispatch("pointerup");
  p.el("muteBtn").dispatch("click");
});
run("reconnect", (p) => { p.ws.close(); p.advance(600); p.connect(); p.tap(); });

process.stdout.write(JSON.stringify(out));
