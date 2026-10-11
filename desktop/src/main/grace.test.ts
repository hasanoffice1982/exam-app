import assert from "node:assert/strict";
import { mock, test } from "node:test";

import { GraceTimer } from "./grace";

test("fires after the grace period", () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  let fired = 0;
  const grace = new GraceTimer(3000);
  grace.start(() => fired++);
  mock.timers.tick(2999);
  assert.equal(fired, 0);
  mock.timers.tick(1);
  assert.equal(fired, 1);
  mock.timers.reset();
});

test("cancel (focus regained in time) prevents firing", () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  let fired = 0;
  const grace = new GraceTimer(3000);
  grace.start(() => fired++);
  mock.timers.tick(1000);
  grace.cancel();
  mock.timers.tick(10_000);
  assert.equal(fired, 0);
  mock.timers.reset();
});

test("a new blur restarts the window and setGraceMs applies to the next one", () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  let fired = 0;
  const grace = new GraceTimer(3000);
  grace.start(() => fired++);
  mock.timers.tick(2000);
  grace.setGraceMs(1000);
  grace.start(() => fired++);
  mock.timers.tick(1000);
  assert.equal(fired, 1);
  mock.timers.reset();
});
