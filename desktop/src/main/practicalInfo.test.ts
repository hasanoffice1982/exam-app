import assert from "node:assert/strict";
import { test } from "node:test";

import { buildPracticalInfo, isOpenableLink } from "./practicalInfo";

const config = (over: Partial<ExamConfig> = {}): ExamConfig =>
  ({
    name: "Physics Lab",
    practical_instructions: "Build the circuit",
    practical_url: "https://example.com/task",
    practical_screenshot_seconds: 45,
    ends_at: "2026-10-12T10:00:00Z",
    server_time: "2026-10-12T09:00:00Z",
    ...over,
  }) as ExamConfig;

test("the deadline is corrected by the gap between the server clock and the student's clock", () => {
  const studentNow = Date.parse("2026-10-12T09:30:00Z"); // student's clock runs 30 min fast
  const info = buildPracticalInfo(config(), studentNow);
  // an hour of server time remains, so an hour remains on the student's (fast) clock too
  assert.equal(info.endsAtMs! - studentNow, 60 * 60 * 1000);
});

test("copies the teacher's settings and handles an exam with no end time", () => {
  const info = buildPracticalInfo(config({ ends_at: null }));
  assert.deepEqual(
    { name: info.examName, text: info.instructions, url: info.url, seconds: info.screenshotSeconds, end: info.endsAtMs },
    { name: "Physics Lab", text: "Build the circuit", url: "https://example.com/task", seconds: 45, end: null },
  );
});

test("only http(s) links can be opened from the practical window", () => {
  assert.equal(isOpenableLink("https://example.com/task"), true);
  assert.equal(isOpenableLink("http://192.168.0.5/task"), true);
  for (const bad of ["", "javascript:alert(1)", "file:///etc/passwd", "ftp://x/y", "not a url", "data:text/html,x"]) {
    assert.equal(isOpenableLink(bad), false, bad);
  }
});
