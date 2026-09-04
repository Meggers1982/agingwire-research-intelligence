/* Runs the dashboard's inline script against stub DOM and fetch, so a
   ReferenceError, a typo or a renamed field fails in CI rather than showing the
   reader a blank page under a green pipeline.

   Usage: node dashboard_harness.mjs <script.js> <template.html> <data-dir>
   Prints the rendered main innerHTML on success; exits non-zero on any error. */

import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import vm from "node:vm";

const [scriptPath, templatePath, dataDir] = process.argv.slice(2);
const source = readFileSync(scriptPath, "utf8");
const template = readFileSync(templatePath, "utf8");

/* Only ids that exist in the markup resolve, so a lookup for an element the
   template does not have is a failure rather than a silent stub. Ids written
   into innerHTML at render time count too -- that is where most of them live. */
const staticIds = new Set([...template.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
const liveIds = new Set(staticIds);
const noteIds = html => {
  for (const m of String(html).matchAll(/\bid="([^"]+)"/g)) liveIds.add(m[1]);
};

const makeEl = (id = "") => {
  const el = {
    id,
    _html: "",
    value: "",
    dataset: {},
    style: { setProperty() {}, removeProperty() {} },
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    scrollIntoView() {}, focus() {}, blur() {}, remove() {}, click() {},
    appendChild() {}, removeChild() {}, insertBefore() {}, setAttribute() {},
    getAttribute: () => null, hasAttribute: () => false, closest: () => null,
    addEventListener() {}, removeEventListener() {},
    getBoundingClientRect: () => ({ height: 91, top: 0, bottom: 91, width: 1440 }),
    querySelector: () => null,
    querySelectorAll: () => [],
    textContent: "",
    offsetHeight: 91,
    options: [],          // <select>
    selectedIndex: 0,
    checked: false,
    disabled: false,
    children: [],
  };
  Object.defineProperty(el, "innerHTML", {
    get: () => el._html,
    set: v => { el._html = String(v); noteIds(v); },
  });
  return el;
};

const elements = new Map();
const getEl = id => {
  if (!liveIds.has(id)) return null;
  if (!elements.has(id)) elements.set(id, makeEl(id));
  return elements.get(id);
};

const documentStub = {
  getElementById: getEl,
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  createElement: () => makeEl(),
  documentElement: makeEl("html"),
  body: makeEl("body"),
  head: makeEl("head"),
  activeElement: null,
  addEventListener() {}, removeEventListener() {},
};

const store = new Map();
const localStorageStub = {
  getItem: k => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: k => store.delete(k),
};

const fetchStub = async url => {
  const name = String(url).replace(/^\.?\//, "");
  const file = join(dataDir, name);
  if (!existsSync(file)) return { ok: false, status: 404, json: async () => ({}) };
  const body = readFileSync(file, "utf8");
  return { ok: true, status: 200, json: async () => JSON.parse(body), text: async () => body };
};

const failures = [];
const windowStub = {
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  scrollTo() {}, scrollY: 0, innerHeight: 900, innerWidth: 1440,
  location: { href: "https://example.test/", hash: "" },
  requestAnimationFrame: cb => cb(),
};

const sandbox = {
  document: documentStub,
  window: windowStub,
  localStorage: localStorageStub,
  sessionStorage: localStorageStub,
  fetch: fetchStub,
  console,
  setTimeout, clearTimeout, setInterval, clearInterval,
  Blob: class { constructor() {} },
  URL: { createObjectURL: () => "blob:stub", revokeObjectURL() {} },
  navigator: { userAgent: "node", clipboard: { writeText: async () => {} } },
  alert() {}, requestAnimationFrame: cb => cb(),
};
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
Object.assign(windowStub, { document: documentStub, localStorage: localStorageStub });

process.on("unhandledRejection", err => failures.push(`unhandled rejection: ${err && err.stack || err}`));
process.on("uncaughtException", err => failures.push(`uncaught exception: ${err && err.stack || err}`));

try {
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "dashboard.js" });
} catch (err) {
  console.error(`SCRIPT ERROR: ${err.stack || err}`);
  process.exit(1);
}

// boot() is async and not awaited by the script; drain the microtask queue.
for (let i = 0; i < 50; i++) await new Promise(resolve => setImmediate(resolve));

if (failures.length) {
  console.error(`RUNTIME ERROR: ${failures.join("\n")}`);
  process.exit(1);
}

const main = getEl("main");
if (!main || !main.innerHTML.trim()) {
  console.error("RENDER ERROR: main was never populated");
  process.exit(1);
}
process.stdout.write(main.innerHTML);
