import assert from "node:assert/strict";
import { test } from "node:test";

import { averageBrightness, dataUrlToBuffer, friendlyCameraError, isTooDark, nextDelayMs, withTimeout } from "./webcamUtils";

test("next photo delay is randomised within +/-50% of the interval", () => {
  assert.equal(nextDelayMs(180, () => 0), 90_000);
  assert.equal(nextDelayMs(180, () => 0.5), 180_000);
  assert.equal(nextDelayMs(180, () => 0.999), 269_820);
});

test("intervals below the 30 s floor are raised to it", () => {
  assert.equal(nextDelayMs(1, () => 0.5), 30_000);
});

test("only JPEG data URLs with content are accepted", () => {
  const url = "data:image/jpeg;base64," + Buffer.from("jpeg-bytes").toString("base64");
  assert.equal(dataUrlToBuffer(url).toString(), "jpeg-bytes");
  assert.throws(() => dataUrlToBuffer("data:image/png;base64,AAAA"), /unexpected image format/);
  assert.throws(() => dataUrlToBuffer("nonsense"), /unexpected image format/);
  assert.throws(() => dataUrlToBuffer("data:image/jpeg;base64,"), /unexpected image format/);
});

test("brightness: black frame is too dark, normal frame is not", () => {
  const frame = (value: number, pixels = 192) => Buffer.alloc(pixels * 4, value);
  assert.equal(averageBrightness(frame(0)), 0);
  assert.equal(isTooDark(averageBrightness(frame(0))), true);
  assert.equal(isTooDark(averageBrightness(frame(5))), true);
  assert.equal(isTooDark(averageBrightness(frame(120))), false);
  assert.equal(averageBrightness(Buffer.alloc(0)), 0);
});

test("brightness ignores the alpha channel", () => {
  const opaqueBlack = Buffer.from([0, 0, 0, 255, 0, 0, 0, 255]);
  assert.equal(averageBrightness(opaqueBlack), 0);
});

test("camera errors become short, student-readable reasons", () => {
  assert.equal(friendlyCameraError("NotAllowedError: Permission denied"), "Camera access was denied");
  assert.equal(friendlyCameraError("NotFoundError: Requested device not found"), "No camera found");
  assert.equal(friendlyCameraError("NotReadableError: Could not start video source"), "Camera is in use by another app");
  assert.equal(friendlyCameraError("Camera image is black (covered)"), "Camera image is black (lens covered?)");
  assert.equal(friendlyCameraError("Error invoking remote method 'x': Error: weird thing"), "weird thing");
  assert.equal(friendlyCameraError(""), "Camera error");
});

test("withTimeout passes through results and errors, and rejects when work hangs", async () => {
  assert.equal(await withTimeout(Promise.resolve(7), 1000, "late"), 7);
  await assert.rejects(withTimeout(Promise.reject(new Error("boom")), 1000, "late"), /boom/);
  await assert.rejects(withTimeout(new Promise(() => undefined), 20, "Camera did not respond"), /did not respond/);
  assert.equal(friendlyCameraError("Camera did not respond"), "Camera did not respond");
});
