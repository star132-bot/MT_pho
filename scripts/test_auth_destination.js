#!/usr/bin/env node
"use strict";

// Exercise the actual browser helper without initializing forms or contacting
// an identity provider. URL follows the browser's normalization rules.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../auth.js"), "utf8");
const start = source.indexOf("function safeInternalPath(");
const end = source.indexOf("\nfunction setFieldVisibility", start);
assert.ok(start >= 0 && end > start, "Authentication destination helper must exist");
const context = {
  URL,
  window: { location: { origin: "https://mtdo.cn" } },
  DEFAULT_AUTH_DESTINATION: "/works.html",
  BLOCKED_NEXT_PATHS: new Set(["/auth/sign-in", "/auth/mfa"]),
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);

const rejected = [
  "https://example.test/steal", "//example.test/steal",
  "/%2fexample.test", "/%252fexample.test",
  "/%5cexample.test", "/%255cexample.test",
  "/works.html\r\nInjected: bad", "/works.html\x00",
  "/works.html?x=%0a", "/works.html?x=%250d%250a",
  "/public/../auth/oauth/google", "/public/%2e%2e/api/me",
  "/%61uth/sign-in", "/%2561uth/sign-in",
  "/api/me", "/auth", "/api",
  "/%3F/../auth/oauth/google", "/%23/../api/me",
  "/%253F/../auth/oauth/google", "/%2523/../api/me",
];
for (const [index, destination] of rejected.entries()) {
  assert.equal(context.safeInternalPath(destination), "/works.html", `Reject unsafe destination ${index + 1}`);
}

const accepted = [
  "/settings/account", "/workspace/images",
  "/workspace/images?filter=drafts#list",
  "/workspace/images?query=50%25",
  "/workspace/images?query=50%2525",
  "/works.html?work=example#details",
];
for (const [index, destination] of accepted.entries()) {
  assert.equal(context.safeInternalPath(destination), destination, `Preserve safe destination ${index + 1}`);
}
assert.equal(context.safeInternalPath("/workspace/../settings/account"), "/settings/account");
console.log("Authentication browser destination boundaries passed.");
