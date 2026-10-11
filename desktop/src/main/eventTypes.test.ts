import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";

import { EventType } from "./eventTypes";

test("client event names match the backend's EventType (except the server-only ones)", () => {
  const file = path.join(__dirname, "..", "..", "..", "backend", "apps", "proctoring", "event_types.py");
  const server = new Set([...readFileSync(file, "utf8").matchAll(/=\s*"([a-z_]+)"/g)].map((m) => m[1]));
  const client = new Set<string>(Object.values(EventType));

  assert.deepEqual([...client].filter((v) => !server.has(v)), [], "client sends an event the server doesn't know");
  assert.deepEqual([...server].filter((v) => !client.has(v)).sort(), ["exam_resumed", "force_ended", "stage_advanced", "time_extended"], "server has events the client lacks");
});
