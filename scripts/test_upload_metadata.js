#!/usr/bin/env node
// Network-free checks for upload prefill: embedded IPTC title, caption and
// keywords (as written by Lightroom/Photoshop) and filename-derived titles.
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "archive-upload.js"), "utf8");
const window = {};
new Function("window", source)(window);
const { readEmbeddedMetadata, titleFromFilename } = window.MTArchiveUpload;

function iptcDataset(dataset, text) {
  const bytes = Buffer.from(text, "utf8");
  return Buffer.concat([Buffer.from([0x1c, 2, dataset, bytes.length >> 8, bytes.length & 0xff]), bytes]);
}

function jpegWithIptc(datasets) {
  const utf8Marker = Buffer.from([0x1c, 1, 90, 0, 3, 0x1b, 0x25, 0x47]);
  const iptc = Buffer.concat([utf8Marker, ...datasets]);
  const header = Buffer.alloc(12);
  header.write("8BIM", 0, "ascii");
  header.writeUInt16BE(0x0404, 4);
  header.writeUInt16BE(0, 6); // empty, padded resource name
  header.writeUInt32BE(iptc.length, 8);
  const resource = Buffer.concat([header, iptc, Buffer.alloc(iptc.length % 2)]);
  const payload = Buffer.concat([Buffer.from("Photoshop 3.0\0", "ascii"), resource]);
  const segment = Buffer.concat([Buffer.from([0xff, 0xed, (payload.length + 2) >> 8, (payload.length + 2) & 0xff]), payload]);
  const file = Buffer.concat([Buffer.from([0xff, 0xd8]), segment, Buffer.from([0xff, 0xda, 0, 2, 0xff, 0xd9])]);
  return file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength);
}

const photo = jpegWithIptc([
  iptcDataset(5, "Grey Heron at Dawn"),
  iptcDataset(120, "A heron waits in the reeds  before sunrise."),
  iptcDataset(25, "bird"),
  iptcDataset(25, "Heron"),
  iptcDataset(25, "heron"),
  iptcDataset(25, "黑白"),
]);
assert.deepStrictEqual(readEmbeddedMetadata(photo, "image/jpeg"), {
  title: "Grey Heron at Dawn",
  caption: "A heron waits in the reeds before sunrise.",
  keywords: ["bird", "Heron", "黑白"],
});

// IPTC is JPEG-only; files without metadata (or other formats) fall back cleanly.
assert.deepStrictEqual(readEmbeddedMetadata(photo, "image/png"), { title: "", caption: "", keywords: [] });
const plain = Buffer.from([0xff, 0xd8, 0xff, 0xda, 0, 2, 0xff, 0xd9]);
assert.deepStrictEqual(readEmbeddedMetadata(plain.buffer.slice(plain.byteOffset, plain.byteOffset + plain.length), "image/jpeg"), {
  title: "",
  caption: "",
  keywords: [],
});

assert.strictEqual(titleFromFilename("grey-heron_at-dawn.jpg"), "Grey Heron At Dawn");
assert.strictEqual(titleFromFilename("DSC_0042.JPG"), "DSC 0042");
assert.strictEqual(titleFromFilename("Snowy Owl  (B&W).webp"), "Snowy Owl (B&W)");
assert.strictEqual(titleFromFilename(".jpg"), "");

console.log("Upload metadata checks passed (IPTC title/caption/keywords, filename titles).");
