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
  AbortController,
  setTimeout,
  clearTimeout,
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

function isolatedArchive(overrides = {}) {
  const context = {
    window: { MTPresenceArchiveData: { sampleItems: [{ id: "sample", src: "/sample.jpg" }] }, dispatchEvent() {} },
    localStorage: new MemoryStorage(),
    sessionStorage: new MemoryStorage(),
    CustomEvent: TestCustomEvent,
    AbortController, setTimeout, clearTimeout,
    fetch: async () => ({ ok: true, json: async () => ({ source: "supabase-public", items: [] }) }),
    ...overrides,
  };
  if (overrides.storageBlocked) {
    for (const key of ["localStorage", "sessionStorage"]) {
      Object.defineProperty(context, key, { get() { throw new Error("Storage blocked"); } });
    }
  }
  vm.runInNewContext(source, context);
  return context.window.MTPresencePublicArchive;
}

async function testRecoveryBoundaries() {
  const blocked = isolatedArchive({ storageBlocked: true });
  assert.deepEqual(Array.from(blocked.readLightboxIds()), []);
  assert.deepEqual(Array.from(blocked.readInquirySelectionIds()), []);
  assert.throws(() => blocked.writeLightboxIds(["a"]));

  const quotaStorage = new MemoryStorage();
  quotaStorage.setItem("mt-presence-lightbox-v1", '["saved"]');
  quotaStorage.setItem = () => { throw new Error("Quota exceeded"); };
  const quota = isolatedArchive({ localStorage: quotaStorage });
  assert.throws(() => quota.toggleLightboxId("other"), /Quota exceeded/);
  assert.deepEqual(Array.from(quota.readLightboxIds()), ["saved"]);

  const empty = await isolatedArchive().loadPublishedWorks();
  assert.equal(empty.authoritative, true);
  assert.equal(empty.works.length, 0);
  assert.equal(empty.error, undefined);

  for (const payload of [{}, { items: [null] }, { items: [{ id: "private", assets: [{ kind: "original", url: "/private.jpg" }] }] }]) {
    const result = await isolatedArchive({ fetch: async () => ({ ok: true, json: async () => payload }) }).loadPublishedWorks();
    assert.equal(result.error, true);
    assert.equal(result.authoritative, true);
    assert.equal(result.works.length, 0);
  }
  const failed = await isolatedArchive({ fetch: async () => ({ ok: false, json: async () => ({ source: "local-sqlite", error: { message: "Unavailable" } }) }) }).loadPublishedWorks();
  assert.equal(failed.error, true);
  assert.equal(failed.works.length, 0);

  const timedOut = await isolatedArchive({
    setTimeout(callback) { queueMicrotask(callback); return 1; },
    clearTimeout() {},
    fetch: (_url, { signal }) => new Promise((_resolve, reject) => signal.addEventListener("abort", () => {
      const error = new Error("Aborted"); error.name = "AbortError"; reject(error);
    })),
  }).loadPublishedWorks();
  assert.equal(timedOut.error, true);
  assert.match(timedOut.status, /timed out/);
  console.log("public_storage_failure_recovery=yes");
  console.log("public_authoritative_error_not_empty=yes");
  console.log("public_archive_timeout=yes");
}

testRecoveryBoundaries().catch((error) => { console.error(error); process.exitCode = 1; });
