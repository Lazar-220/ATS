import assert from "node:assert/strict";
import { test } from "node:test";

import { healthState } from "./health.ts";

test("no answer yet means checking", () => {
  assert.equal(healthState({ isPending: true, isError: false, data: undefined }), "checking");
});

test("a healthy answer is ok", () => {
  const data = { status: "ok", database: "reachable" } as const;
  assert.equal(healthState({ isPending: false, isError: false, data }), "ok");
});

test("the 503 body with the database down is degraded, not unreachable", () => {
  const data = { status: "degraded", database: "unreachable" } as const;
  assert.equal(healthState({ isPending: false, isError: false, data }), "degraded");
});

test("either part being off is degraded", () => {
  assert.equal(
    healthState({ isPending: false, isError: false, data: { status: "degraded", database: "reachable" } }),
    "degraded",
  );
  assert.equal(
    healthState({ isPending: false, isError: false, data: { status: "ok", database: "unreachable" } }),
    "degraded",
  );
});

test("a failed request is unreachable, also when an older answer is still held", () => {
  assert.equal(healthState({ isPending: false, isError: true, data: undefined }), "unreachable");
  const stale = { status: "ok", database: "reachable" } as const;
  assert.equal(healthState({ isPending: false, isError: true, data: stale }), "unreachable");
});
