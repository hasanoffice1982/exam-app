import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { api, ApiError, isRetryable, setToken } from "./api";
import { createSender } from "./sync";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
  setToken(null);
});

function mockFetch(status: number, body: unknown = {}, capture?: (init: RequestInit) => void) {
  globalThis.fetch = (async (_url: unknown, init: RequestInit) => {
    capture?.(init);
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
}

test("isRetryable: network, 5xx, 429 retry; other 4xx do not", () => {
  assert.equal(isRetryable(new TypeError("fetch failed")), true);
  assert.equal(isRetryable(new ApiError("x", 503)), true);
  assert.equal(isRetryable(new ApiError("x", 429)), true);
  assert.equal(isRetryable(new ApiError("x", 400)), false);
  assert.equal(isRetryable(new ApiError("x", 401)), false);
});

test("sends the bearer token once set, never before", async () => {
  let headers: Headers | undefined;
  mockFetch(200, [], (init) => (headers = new Headers(init.headers)));
  await api.listExams();
  assert.equal(headers?.get("Authorization"), null);
  setToken("abc");
  await api.listExams();
  assert.equal(headers?.get("Authorization"), "Bearer abc");
});

test("surfaces DRF error messages", async () => {
  mockFetch(401, { detail: "Invalid roll number or password." });
  await assert.rejects(api.login("1", "x", ""), /Invalid roll number or password\./);
  mockFetch(400, { exam_id: ["Object with exam_id=zz does not exist."] });
  await assert.rejects(api.postEvent({}), /does not exist/);
});

test("login sends the honeypot field to the server", async () => {
  let sent: Record<string, string> = {};
  mockFetch(200, { token: "t", roll_number: "1", name: "A" }, (init) => (sent = JSON.parse(init.body as string)));
  await api.login("1", "pw", "");
  assert.deepEqual(Object.keys(sent).sort(), ["password", "roll_number", "website"]);
});

test("sender maps responses to queue outcomes and sends client_id", async () => {
  let unauthorized = 0;
  const send = createSender(() => unauthorized++);
  const item = { id: "11111111-1111-4111-8111-111111111111", owner: "1", kind: "event" as const, fields: { event_type: "x" } };

  let body: Record<string, string> = {};
  mockFetch(201, {}, (init) => (body = JSON.parse(init.body as string)));
  assert.equal(await send(item), "done");
  assert.equal(body.client_id, item.id);

  mockFetch(200); // duplicate replay is also success
  assert.equal(await send(item), "done");
  mockFetch(500);
  assert.equal(await send(item), "retry");
  mockFetch(429);
  assert.equal(await send(item), "retry");
  mockFetch(400, { detail: "bad" });
  assert.equal(await send(item), "drop");
  mockFetch(401, { detail: "Session expired." });
  assert.equal(await send(item), "drop");
  assert.equal(unauthorized, 1);

  globalThis.fetch = (async () => {
    throw new TypeError("fetch failed");
  }) as typeof fetch;
  assert.equal(await send(item), "retry");
});

test("startExam posts to the per-exam start endpoint and surfaces server refusals", async () => {
  let url = "";
  let method = "";
  globalThis.fetch = (async (u: string, init: RequestInit) => {
    url = u;
    method = init.method ?? "";
    return new Response(JSON.stringify({ form_url: "https://f", monitoring_enabled: true }), { status: 200 });
  }) as typeof fetch;
  await api.startExam("math 101");
  assert.match(url, /\/api\/exams\/math%20101\/start\/$/);
  assert.equal(method, "POST");

  mockFetch(403, { detail: "Your teacher ended your attempt. Contact them to continue." });
  await assert.rejects(api.startExam("math-101"), /teacher ended your attempt/);
  mockFetch(403, { detail: "This exam is not assigned to your batch." });
  await assert.rejects(api.startExam("math-101"), /batch/);
});

test("sender uploads webcam jpegs with an image/jpeg part and the kind field", async () => {
  const send = createSender(() => undefined);
  let form: FormData | undefined;
  globalThis.fetch = (async (_u: unknown, init: RequestInit) => {
    form = init.body as FormData;
    return new Response("{}", { status: 201 });
  }) as typeof fetch;
  const item = { id: "22222222-2222-4222-8222-222222222222", owner: "1", kind: "screenshot" as const, fields: { kind: "webcam" }, file: "/tmp/x/22222222.jpg" };
  assert.equal(await send(item, Buffer.from("jpeg")), "done");
  const file = form!.get("file") as File;
  assert.equal(file.type, "image/jpeg");
  assert.equal(file.name, `${item.id}.jpg`);
  assert.equal(form!.get("kind"), "webcam");
  assert.equal(form!.get("client_id"), item.id);
});

test("activate sends the honeypot field and only returns the masked address", async () => {
  let sent: Record<string, string> = {};
  mockFetch(200, { detail: "We emailed your password to a***@x.com.", email: "a***@x.com" }, (init) => (sent = JSON.parse(init.body as string)));
  const result = await api.activate("1", "ann@x.com", "");
  assert.deepEqual(result, { detail: "We emailed your password to a***@x.com.", email: "a***@x.com" });
  assert.deepEqual(Object.keys(sent).sort(), ["email", "roll_number", "website"]);
  mockFetch(503, { detail: "We could not send the email. Please try again in a minute or tell your teacher." });
  await assert.rejects(api.activate("1", "ann@x.com", ""), /could not send the email/);
  mockFetch(409, { detail: "This account is already activated. Log in with your password, or ask your teacher to reset it." });
  await assert.rejects(api.activate("1", "ann@x.com", ""), /already activated/);
});

test("profile, change-password and logout use the session and surface server messages", async () => {
  setToken("tok");
  let seen: { url: string; method: string; auth: string | null; body: string } = { url: "", method: "", auth: null, body: "" };
  globalThis.fetch = (async (u: string, init: RequestInit) => {
    seen = { url: u, method: init.method ?? "GET", auth: new Headers(init.headers).get("Authorization"), body: String(init.body ?? "") };
    return new Response(JSON.stringify({ roll_number: "1", name: "Ann", email: "a***@x.com", batch: 81 }), { status: 200 });
  }) as typeof fetch;
  assert.deepEqual(await api.getProfile(), { roll_number: "1", name: "Ann", email: "a***@x.com", batch: 81 });
  assert.match(seen.url, /\/api\/profile\/$/);
  assert.equal(seen.auth, "Bearer tok");

  await api.changePassword("old-pass", "new-pass-123");
  assert.match(seen.url, /\/api\/auth\/change-password\/$/);
  assert.deepEqual(JSON.parse(seen.body), { current_password: "old-pass", new_password: "new-pass-123" });

  await api.logout();
  assert.match(seen.url, /\/api\/auth\/logout\/$/);
  assert.equal(seen.method, "POST");

  mockFetch(400, { detail: "Your current password is not correct." });
  await assert.rejects(api.changePassword("x", "y"), /current password is not correct/);
  mockFetch(429, { detail: "Too many failed attempts. Try again in 15 minutes." });
  await assert.rejects(api.changePassword("x", "y"), /Too many failed attempts/);
});

test("advanceStage posts to the advance endpoint and returns the new config", async () => {
  let url = "";
  globalThis.fetch = (async (u: string, init: RequestInit) => {
    url = `${init.method} ${u}`;
    return new Response(JSON.stringify({ stage: "practical", practical_enabled: true }), { status: 200 });
  }) as typeof fetch;
  const config = await api.advanceStage("lab 1");
  assert.match(url, /^POST .*\/api\/exams\/lab%201\/advance\/$/);
  assert.equal(config.stage, "practical");
  mockFetch(400, { detail: "This exam has no practical part." });
  await assert.rejects(api.advanceStage("x"), /no practical part/);
  mockFetch(403, { detail: "You quit this exam and cannot re-enter it." });
  await assert.rejects(api.advanceStage("x"), /cannot re-enter/);
});
