import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError } from "./api";
import { describeError } from "./errors";

const OFFLINE = "Cannot reach the exam server. Check your network connection and try again.";

test("server messages are shown exactly as the server wrote them", () => {
  assert.equal(describeError(new ApiError("Invalid roll number or password.", 401)), "Invalid roll number or password.");
  assert.equal(describeError(new ApiError("You quit this exam and cannot re-enter it.", 403)), "You quit this exam and cannot re-enter it.");
});

test("network failures become one plain sentence", () => {
  const dns = Object.assign(new TypeError("fetch failed"), { cause: { code: "ENOTFOUND" } });
  assert.equal(describeError(dns), OFFLINE);
  assert.equal(describeError(Object.assign(new Error("x"), { name: "TimeoutError" })), OFFLINE);
  assert.equal(describeError(Object.assign(new Error("x"), { name: "AbortError" })), OFFLINE);
  assert.equal(describeError(new TypeError("fetch failed")), OFFLINE);
  assert.equal(describeError(Object.assign(new Error("connect"), { cause: { code: "ECONNREFUSED" } })), OFFLINE);
  assert.equal(describeError(new Error("Network request failed")), OFFLINE);
});

test("other errors keep their own message", () => {
  assert.equal(describeError(new Error("Please close OBS Studio before starting the exam.")), "Please close OBS Studio before starting the exam.");
  assert.equal(describeError("plain text"), "plain text");
});
