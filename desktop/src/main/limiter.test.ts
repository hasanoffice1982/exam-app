import assert from "node:assert/strict";
import { test } from "node:test";

import { AttemptLimiter } from "./limiter";

test("allows one report per key per interval", () => {
  let now = 1000;
  const limiter = new AttemptLimiter(5000, () => now);
  assert.equal(limiter.allow("clipboard_attempt"), true);
  now += 4999;
  assert.equal(limiter.allow("clipboard_attempt"), false);
  now += 1;
  assert.equal(limiter.allow("clipboard_attempt"), true);
});

test("keys are limited independently", () => {
  const limiter = new AttemptLimiter(5000, () => 0);
  assert.equal(limiter.allow("clipboard_attempt"), true);
  assert.equal(limiter.allow("devtools_attempt"), true);
  assert.equal(limiter.allow("clipboard_attempt"), false);
});
