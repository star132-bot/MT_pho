#!/usr/bin/env node

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }
}

class TestCustomEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.detail = options.detail;
  }
}

const localStorage = new MemoryStorage();
const sessionStorage = new MemoryStorage();
const events = [];
const window = {
  MTPresenceArchiveData: {},
  dispatchEvent(event) {
    events.push(event);
  },
};

const source = fs.readFileSync(path.join(__dirname, "..", "public-archive.js"), "utf8");
vm.runInNewContext(source, {
  window,
  localStorage,
  sessionStorage,
  CustomEvent: TestCustomEvent,
  fetch: async () => {
    throw new Error("Network access is not part of this state contract.");
  },
});

const archive = window.MTPresencePublicArchive;
assert.deepEqual(Array.from(archive.readLightboxIds()), []);
assert.deepEqual(Array.from(archive.readInquirySelectionIds()), []);

archive.writeLightboxIds(["work-a", "work-b", "work-c", "work-d"]);
assert.deepEqual(
  Array.from(archive.writeInquirySelectionIds(["work-a", "work-c", "not-saved", "work-a"])),
  ["work-a", "work-c"],
);

archive.writeLightboxIds(["work-b", "work-c", "work-d"]);
assert.deepEqual(Array.from(archive.readInquirySelectionIds()), ["work-c"]);

archive.toggleLightboxId("work-c");
assert.deepEqual(Array.from(archive.readLightboxIds()), ["work-b", "work-d"]);
assert.deepEqual(Array.from(archive.readInquirySelectionIds()), []);

assert.ok(events.some((event) => event.type === "mt:lightbox-change"));
assert.ok(events.some((event) => event.type === "mt:inquiry-selection-change"));
console.log("public_interaction_state=yes");
