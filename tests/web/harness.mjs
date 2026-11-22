// Runs the phone page script (web/app.js) in Node with a small fake browser: elements, a fake
// WebSocket that records what the page sends, and timers and animation frames the test advances
// by hand. No real browser or helper is needed.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const APP_DIR = path.resolve(process.env.APP_ROOT || path.join(here, "..", "..", "desktop"));
const APP_JS = fs.readFileSync(path.join(APP_DIR, "web", "app.js"), "utf8");

class ClassList {
  constructor() { this.set = new Set(); }
  add(c) { this.set.add(c); }
  remove(c) { this.set.delete(c); }
  contains(c) { return this.set.has(c); }
  toggle(c, force) {
    const on = force === undefined ? !this.set.has(c) : !!force;
    if (on) this.set.add(c); else this.set.delete(c);
    return on;
  }
}

class El {
  constructor(page, id, attrs = {}) {
    this.page = page;
    this.id = id;
    this.listeners = {};
    this.classList = new ClassList();
    this.attrs = {};
    this.style = {};
    this.dataset = attrs.dataset || {};
    this.hidden = !!attrs.hidden;
    this.value = attrs.value ?? "";
    this.checked = false;
    this.textContent = "";
    this.open = false;
    this.children = [];
    this.captured = new Set();
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatch(type, props = {}) {
    const ev = {
      type, target: props.target || this, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }, ...props,
    };
    for (const fn of this.listeners[type] || []) fn(ev);
    return ev;
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  setPointerCapture(id) { this.captured.add(id); }
  focus() {
    if (this.page.document.activeElement === this) return;
    const prev = this.page.document.activeElement;
    this.page.document.activeElement = this;
    if (prev && prev !== this) prev.dispatch("blur");
    this.dispatch("focus");
  }
  blur() {
    if (this.page.document.activeElement !== this) return;
    this.page.document.activeElement = null;
    this.dispatch("blur");
  }
  setSelectionRange() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  closest(sel) { return sel === "button" && this.isButton ? this : null; }
  querySelectorAll(sel) {
    const m = /^\[data-(\w+)\]$/.exec(sel);
    return this.children.filter((c) => m && c.dataset[m[1]] !== undefined);
  }
}

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  constructor(page, url) {
    this.page = page;
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.sent = [];
    page.sockets.push(this);
  }
  send(data) { this.sent.push(JSON.parse(data)); this.page.sent.push(JSON.parse(data)); }
  close() {
    if (this.readyState === FakeWebSocket.CLOSED) return;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose && this.onclose({});
  }
  // test side
  serverOpen() { this.readyState = FakeWebSocket.OPEN; this.onopen && this.onopen({}); }
  serverSend(msg) { this.onmessage && this.onmessage({ data: JSON.stringify(msg) }); }
}

export class Page {
  constructor({ storage = {}, hash = "", userAgent = "Mozilla/5.0 (iPhone)" } = {}) {
    this.now = 1000;           // ms, drives Date.now, performance.now and event timestamps
    this.timers = [];
    this.timerSeq = 0;
    this.frames = [];
    this.sent = [];
    this.sockets = [];
    this.vibrations = 0;
    this.storage = { ...storage };
    this.historyCalls = [];
    this.els = {};
    const page = this;

    this.document = {
      activeElement: null,
      visibilityState: "visible",
      listeners: {},
      getElementById: (id) => page.el(id),
      addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    };

    // Elements the script looks up, with the attributes index.html gives them.
    for (const id of ["volBtn", "volRow", "keys", "cmdKey", "spkOff", "pairErr"]) this.el(id).hidden = true;
    this.el("kbd");
    const keys = this.el("keys");
    for (const k of ["esc", "tab", "left", "up", "down", "right", "delete"]) this.addKey({ key: k });
    for (const m of ["ctrl", "alt", "shift", "cmd"]) this.addKey({ mod: m });
    this.addKey({ action: "close" });
    this.el("volSlider").value = "50";
    this.el("speed");
    this.el("natural");
    void keys;

    const location = { hash, protocol: "http:", host: "192.168.1.15:8765", pathname: "/" };
    const ctx = {
      console,
      document: this.document,
      location,
      history: { replaceState: (...a) => { page.historyCalls.push(a); location.hash = ""; } },
      navigator: { userAgent, vibrate: () => { page.vibrations++; return true; } },
      localStorage: {
        getItem: (k) => (k in page.storage ? page.storage[k] : null),
        setItem: (k, v) => { page.storage[k] = String(v); },
      },
      WebSocket: Object.assign(function (url) { return new FakeWebSocket(page, url); }, {
        CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3,
      }),
      URLSearchParams,
      Math, JSON, Set, Map, Date: { now: () => page.now },
      performance: { now: () => page.now },
      requestAnimationFrame: (fn) => { page.frames.push(fn); return page.frames.length; },
      setTimeout: (fn, ms = 0) => page.addTimer(fn, ms, false),
      setInterval: (fn, ms = 0) => page.addTimer(fn, ms, true),
      clearTimeout: (id) => { page.timers = page.timers.filter((t) => t.id !== id); },
      window: null,
    };
    ctx.window = { innerHeight: 800, visualViewport: undefined };
    ctx.visualViewport = undefined;
    vm.createContext(ctx);
    vm.runInContext(APP_JS, ctx, { filename: "app.js" });
    this.ctx = ctx;
  }

  el(id) { return this.els[id] ||= new El(this, id); }

  addKey(data) {
    const b = new El(this, null, { dataset: data });
    b.isButton = true;
    this.el("keys").children.push(b);
    return b;
  }

  key(data) {
    const [k, v] = Object.entries(data)[0];
    return this.el("keys").children.find((b) => b.dataset[k] === v);
  }

  addTimer(fn, ms, repeat) {
    const id = ++this.timerSeq;
    this.timers.push({ id, fn, at: this.now + ms, ms, repeat });
    return id;
  }

  // Moves the clock forward, running due timers in order.
  advance(ms) {
    const end = this.now + ms;
    for (;;) {
      const due = this.timers.filter((t) => t.at <= end).sort((a, b) => a.at - b.at || a.id - b.id)[0];
      if (!due) break;
      this.now = Math.max(this.now, due.at);
      if (due.repeat) due.at += Math.max(due.ms, 1); else this.timers = this.timers.filter((t) => t !== due);
      due.fn();
    }
    this.now = end;
  }

  frame() {
    const fns = this.frames;
    this.frames = [];
    for (const fn of fns) fn();
  }

  get ws() { return this.sockets[this.sockets.length - 1]; }

  // Opens the socket and answers the page's hello/pair with "paired".
  connect({ os = "mac", name = "Test PC" } = {}) {
    this.ws.serverOpen();
    const first = this.ws.sent[0];
    if (first && (first.t === "hello" || first.t === "pair")) {
      this.ws.serverSend({ t: "paired", token: "tok123", name, os });
    }
    this.sent.length = 0;
    return first;
  }

  // ---------- touch input on the pad ----------
  pointer(type, id, x, y) {
    return this.el("pad").dispatch(type, { pointerId: id, clientX: x, clientY: y, timeStamp: this.now });
  }
  touch(type, touches, changed = touches) {
    const list = (a) => a.map(([x, y]) => ({ clientX: x, clientY: y }));
    return this.el("pad").dispatch(type, { touches: list(type === "touchend" ? [] : touches),
      changedTouches: list(changed), timeStamp: this.now });
  }
  tap(x = 100, y = 100, holdMs = 50) {
    this.touch("touchstart", [[x, y]]);
    this.pointer("pointerdown", 1, x, y);
    this.advance(holdMs);
    this.pointer("pointerup", 1, x, y);
    this.touch("touchend", [], [[x, y]]);
  }
  // One finger from (x, y) along steps of [dx, dy], each `stepMs` apart.
  drag(steps, { x = 100, y = 100, id = 1, stepMs = 16, lift = true } = {}) {
    this.pointer("pointerdown", id, x, y);
    for (const [dx, dy] of steps) {
      this.advance(stepMs);
      x += dx; y += dy;
      this.pointer("pointermove", id, x, y);
      this.frame();
    }
    if (lift) { this.advance(stepMs); this.pointer("pointerup", id, x, y); }
    return [x, y];
  }

  // ---------- keyboard ----------
  type(value) {
    const kbd = this.el("kbd");
    kbd.value = value;
    kbd.dispatch("input");
  }

  msgs(t) { return this.sent.filter((m) => !t || m.t === t); }
}
