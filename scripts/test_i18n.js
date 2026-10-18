#!/usr/bin/env node
// Network-free checks for the visitor English/Chinese switch (i18n.js).
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "i18n.js"), "utf8");

function load({ stored = null, languages = ["en-US"], title = "Works Archive | MT Presence" } = {}) {
  const saved = {};
  let reloaded = false;
  global.Node = { ELEMENT_NODE: 1, TEXT_NODE: 3, DOCUMENT_NODE: 9 };
  global.NodeFilter = { SHOW_ELEMENT: 1, SHOW_TEXT: 4, FILTER_REJECT: 2, FILTER_ACCEPT: 1 };
  global.MutationObserver = class { observe() {} };
  global.document = {
    title,
    documentElement: { dataset: {} },
    body: null,
    createTreeWalker() { return { nextNode() { return null; } }; },
  };
  const window = {
    localStorage: {
      getItem: () => stored,
      setItem: (key, value) => { saved[key] = value; },
    },
    navigator: { languages },
    location: { reload: () => { reloaded = true; } },
  };
  new Function("window", source)(window);
  return { i18n: window.MTPresenceI18n, document: global.document, saved, wasReloaded: () => reloaded };
}

// Default follows the browser language; English pages are left untouched.
let page = load({ languages: ["en-GB"] });
assert.strictEqual(page.i18n.language, "en");
assert.strictEqual(page.i18n.t("Works"), "Works");
assert.strictEqual(page.document.title, "Works Archive | MT Presence");
assert.strictEqual(page.document.documentElement.lang, "en");

page = load({ languages: ["zh-CN", "en"] });
assert.strictEqual(page.i18n.language, "zh");
assert.strictEqual(page.document.documentElement.lang, "zh-CN");
assert.strictEqual(page.document.title, "作品 | MT Presence");

// A remembered choice wins over the browser language.
page = load({ stored: "en", languages: ["zh-CN"] });
assert.strictEqual(page.i18n.language, "en");

// Exact UI strings, surrounding whitespace, and numbered patterns.
page = load({ stored: "zh" });
const { t } = page.i18n;
assert.strictEqual(t("Contact Artist"), "联系艺术家");
assert.strictEqual(t("  Works \n"), "  作品 \n");
assert.strictEqual(t("27 of 27 works"), "显示 27 / 共 27 件作品");
assert.strictEqual(t("3 of 27 works / Abstract + Square"), "显示 3 / 共 27 件作品（抽象 + 方形）");
assert.strictEqual(t("Open full-screen viewer for Grey Heron"), "全屏查看《Grey Heron》");
// Title-shaped patterns apply to accessibility labels only, never page text.
assert.strictEqual(t("View from the Hill"), "View from the Hill");
// Unknown text (for example a photographer's title) is never altered.
assert.strictEqual(t("Grey Heron at Dawn"), "Grey Heron at Dawn");

// Switching stores the choice and reloads; choosing the current language is a no-op.
page.i18n.setLanguage("zh");
assert.strictEqual(page.wasReloaded(), false);
page.i18n.setLanguage("en");
assert.deepStrictEqual(page.saved, { "mt-presence-language": "en" });
assert.strictEqual(page.wasReloaded(), true);
page = load({ stored: "zh" });
page.i18n.setLanguage("fr");
assert.strictEqual(page.wasReloaded(), false);

console.log("Visitor language switch checks passed (detection, memory, dictionary, patterns).");
