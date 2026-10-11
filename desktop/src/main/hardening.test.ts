import assert from "node:assert/strict";
import { test } from "node:test";

import { classifyShortcut, isAllowedUrl, isFormSubmissionUrl, KeyInput } from "./hardening";

const press = (key: string, mods: Partial<KeyInput> = {}): KeyInput => ({
  type: "keyDown",
  key,
  control: false,
  meta: false,
  shift: false,
  alt: false,
  ...mods,
});

test("copy / cut / paste are blocked with Ctrl or Cmd, in either case", () => {
  for (const key of ["c", "x", "v", "C", "V"]) {
    assert.equal(classifyShortcut(press(key, { control: true })), "clipboard_attempt", `ctrl+${key}`);
    assert.equal(classifyShortcut(press(key, { meta: true })), "clipboard_attempt", `cmd+${key}`);
  }
  assert.equal(classifyShortcut(press("Insert", { shift: true })), "clipboard_attempt");
  assert.equal(classifyShortcut(press("Insert", { control: true })), "clipboard_attempt");
  assert.equal(classifyShortcut(press("Delete", { shift: true })), "clipboard_attempt");
});

test("devtools shortcuts are blocked", () => {
  assert.equal(classifyShortcut(press("F12")), "devtools_attempt");
  assert.equal(classifyShortcut(press("I", { control: true, shift: true })), "devtools_attempt");
  assert.equal(classifyShortcut(press("j", { control: true, shift: true })), "devtools_attempt");
  assert.equal(classifyShortcut(press("i", { meta: true, alt: true })), "devtools_attempt");
});

test("view-source, print and save are blocked", () => {
  for (const key of ["u", "p", "s"]) assert.equal(classifyShortcut(press(key, { control: true })), "blocked_shortcut");
});

test("normal typing and navigation keys are untouched", () => {
  for (const key of ["a", "c", "v", "Enter", "Tab", "Backspace", "ArrowDown", "F5", " "]) {
    assert.equal(classifyShortcut(press(key)), null, key);
  }
  assert.equal(classifyShortcut(press("a", { control: true })), null); // select-all stays allowed
  assert.equal(classifyShortcut(press("r", { control: true })), null); // reload stays allowed
});

test("key-up events are ignored so a press is only reported once", () => {
  assert.equal(classifyShortcut({ ...press("v", { control: true }), type: "keyUp" }), null);
});

const FORM = "https://docs.google.com/forms/d/e/abc/viewform";

test("Google Form hosts are allowed", () => {
  for (const url of [
    FORM,
    "https://docs.google.com/forms/d/e/abc/formResponse",
    "https://accounts.google.com/signin",
    "https://www.gstatic.com/forms/x.js",
    "https://lh3.googleusercontent.com/img",
    "https://forms.gle/xyz",
    "https://www.youtube.com/embed/abc",
  ]) {
    assert.equal(isAllowedUrl(url, FORM), true, url);
  }
});

test("other sites, look-alike hosts and non-https schemes are refused", () => {
  for (const url of [
    "https://chat.openai.com/",
    "https://www.google.com.evil.com/",
    "https://evilgoogle.com/",
    "http://docs.google.com/forms/x", // downgrade
    "file:///etc/passwd",
    "javascript:alert(1)",
    "not a url",
  ]) {
    assert.equal(isAllowedUrl(url, FORM), false, url);
  }
});

test("the form's own origin is always allowed, even if not Google (e.g. a local test form)", () => {
  assert.equal(isAllowedUrl("http://127.0.0.1:9000/q2", "http://127.0.0.1:9000/q1"), true);
  assert.equal(isAllowedUrl("http://127.0.0.1:9001/q2", "http://127.0.0.1:9000/q1"), false);
});

test("a Google Form submission is recognised, other pages are not", () => {
  const yes = [
    "https://docs.google.com/forms/d/e/1FAIpQLSabc/formResponse",
    "https://docs.google.com/forms/d/e/1FAIpQLSabc/formResponse?pli=1",
    "https://docs.google.com/forms/u/0/d/e/1FAIpQLSabc/formResponse#x",
  ];
  const no = [
    "https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform",
    "https://docs.google.com/forms/d/e/1FAIpQLSabc/viewform?formResponse",
    "https://docs.google.com/forms/d/e/1FAIpQLSabc/formResponseX",
    "https://evil.example/forms/d/e/abc/formResponse",
    "http://docs.google.com/forms/d/e/abc/formResponse",
    "https://docs.google.com/document/d/abc/formResponse",
  ];
  for (const url of yes) assert.equal(isFormSubmissionUrl(url), true, url);
  for (const url of no) assert.equal(isFormSubmissionUrl(url), false, url);
});
