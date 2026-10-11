import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { beforeEach, test } from "node:test";

import { Outcome, QueueItem, Sender, UploadQueue } from "./queue";

let dir: string;
beforeEach(async () => {
  dir = await fs.mkdtemp(path.join(os.tmpdir(), "queue-test-"));
});

const event = (id: string) => ({ id, kind: "event" as const, fields: { event_type: id } });

function recorder(outcomes: Record<string, Outcome> = {}) {
  const sent: string[] = [];
  const send: Sender = async (item: QueueItem) => {
    sent.push(item.id);
    return outcomes[item.id] ?? "done";
  };
  return { sent, send };
}

async function make(owner = "1", send: Sender = async () => "done", max = 500) {
  const q = new UploadQueue(dir, owner, send, max);
  await q.init();
  return q;
}

test("sends items in FIFO order and empties the queue", async () => {
  const { sent, send } = recorder();
  const q = await make("1", send);
  await q.enqueue(event("a"));
  await q.enqueue(event("b"));
  await q.flush();
  assert.deepEqual(sent, ["a", "b"]);
  assert.equal(q.pending(), 0);
});

test("a retry outcome keeps the item and blocks later ones (order preserved)", async () => {
  const outcomes: Record<string, Outcome> = { a: "retry" };
  const { sent, send } = recorder(outcomes);
  const q = await make("1", send);
  await q.enqueue(event("a"));
  await q.enqueue(event("b"));
  await q.flush();
  assert.deepEqual(sent, ["a"]);
  assert.equal(q.pending(), 2);

  outcomes.a = "done";
  await q.flush();
  assert.deepEqual(sent, ["a", "a", "b"]);
  assert.equal(q.pending(), 0);
});

test("a dropped item is removed and does not block the queue", async () => {
  const { sent, send } = recorder({ a: "drop" });
  const q = await make("1", send);
  await q.enqueue(event("a"));
  await q.enqueue(event("b"));
  await q.flush();
  assert.deepEqual(sent, ["a", "b"]);
  assert.equal(q.pending(), 0);
});

test("pending items survive a restart", async () => {
  const offline = recorder({ a: "retry" });
  const q1 = await make("1", offline.send);
  await q1.enqueue(event("a"));
  await q1.flush();

  const online = recorder();
  const q2 = await make("1", online.send);
  assert.equal(q2.pending(), 1);
  await q2.flush();
  assert.deepEqual(online.sent, ["a"]);
});

test("never sends another student's items, but keeps them", async () => {
  const q1 = await make("1", recorder({ a: "retry" }).send);
  await q1.enqueue(event("a"));
  await q1.flush();

  const { sent, send } = recorder();
  const q2 = await make("2", send);
  await q2.flush();
  assert.deepEqual(sent, []);

  const q1again = await make("1", send);
  await q1again.flush();
  assert.deepEqual(sent, ["a"]);
});

test("screenshot data is passed to the sender and the file is deleted afterwards", async () => {
  let received: Buffer | undefined;
  const q = await make("1", async (_item, data) => {
    received = data;
    return "done";
  });
  await q.enqueue({ id: "s1", kind: "screenshot", fields: {} }, Buffer.from("png-bytes"));
  const file = path.join(dir, "files", "s1.png");
  assert.ok(await fs.stat(file));
  await q.flush();
  assert.equal(received?.toString(), "png-bytes");
  await assert.rejects(fs.stat(file));
});

test("an item whose file vanished is discarded instead of blocking", async () => {
  const { sent, send } = recorder();
  const q = await make("1", send);
  await q.enqueue({ id: "s1", kind: "screenshot", fields: {} }, Buffer.from("x"));
  await q.enqueue(event("b"));
  await fs.unlink(path.join(dir, "files", "s1.png"));
  await q.flush();
  assert.deepEqual(sent, ["b"]);
  assert.equal(q.pending(), 0);
});

test("concurrent flushes do not send an item twice", async () => {
  const { sent, send } = recorder();
  const q = await make("1", send);
  await q.enqueue(event("a"));
  await Promise.all([q.flush(), q.flush(), q.flush()]);
  assert.deepEqual(sent, ["a"]);
});

test("queue is capped, dropping the oldest items", async () => {
  const q = await make("1", async () => "done", 3);
  for (const id of ["a", "b", "c", "d"]) await q.enqueue(event(id));
  assert.equal(q.pending(), 3);
  const { sent, send } = recorder();
  const q2 = await make("1", send, 3);
  await q2.flush();
  assert.deepEqual(sent, ["b", "c", "d"]);
});

test("a corrupt queue file is ignored", async () => {
  await fs.writeFile(path.join(dir, "queue.json"), "{not json");
  const q = await make();
  assert.equal(q.pending(), 0);
});

test("webcam photos keep their jpg extension on disk", async () => {
  const q = await make("1", async () => "done");
  await q.enqueue({ id: "w1", kind: "screenshot", fields: { kind: "webcam" } }, Buffer.from("jpeg"), "jpg");
  assert.ok(await fs.stat(path.join(dir, "files", "w1.jpg")));
  await q.flush();
  await assert.rejects(fs.stat(path.join(dir, "files", "w1.jpg")));
});
