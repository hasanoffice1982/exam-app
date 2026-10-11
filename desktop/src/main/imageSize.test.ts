import assert from "node:assert/strict";
import { test } from "node:test";

import { clampQuality, envInt, fitWithin } from "./imageSize";

test("fitWithin shrinks wide screens and keeps the aspect ratio", () => {
  assert.deepEqual(fitWithin(3840, 2160, 1600), { width: 1600, height: 900 });
  assert.deepEqual(fitWithin(2560, 1440, 1600), { width: 1600, height: 900 });
  assert.deepEqual(fitWithin(1920, 1200, 1600), { width: 1600, height: 1000 });
});

test("fitWithin never scales up", () => {
  assert.deepEqual(fitWithin(1366, 768, 1600), { width: 1366, height: 768 });
  assert.deepEqual(fitWithin(1600, 900, 1600), { width: 1600, height: 900 });
});

test("fitWithin never returns a zero height", () => {
  assert.equal(fitWithin(10000, 1, 100).height, 1);
});

test("quality is kept in a sane range", () => {
  assert.equal(clampQuality(0), 10);
  assert.equal(clampQuality(70.4), 70);
  assert.equal(clampQuality(500), 100);
});

test("envInt falls back on missing or bad values", () => {
  assert.equal(envInt(undefined, 1600), 1600);
  assert.equal(envInt("", 1600), 1600);
  assert.equal(envInt("abc", 1600), 1600);
  assert.equal(envInt("-5", 1600), 1600);
  assert.equal(envInt("1200", 1600), 1200);
});
