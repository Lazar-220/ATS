import assert from "node:assert/strict";
import { test } from "node:test";

import { failedMandatoryLabel, formatScore, statusLabel } from "./ranking.ts";

test("a failed assessment shows no score, never zero", () => {
  assert.equal(formatScore({ status: "failed", score: null }), "–");
  assert.equal(formatScore({ status: "failed", score: 0 }), "–");
  assert.equal(formatScore({ status: "done", score: 87.5 }), "87.5");
  assert.equal(formatScore({ status: "done", score: 0 }), "0.0");
});

test("the failed-mandatory column says it in words", () => {
  assert.equal(failedMandatoryLabel({ status: "done", mandatory_failed: true }), "Mandatory requirement not met");
  assert.equal(failedMandatoryLabel({ status: "done", mandatory_failed: false }), "No");
  assert.equal(failedMandatoryLabel({ status: "failed", mandatory_failed: false }), "–");
});

test("status labels", () => {
  assert.equal(statusLabel("done"), "Assessed");
  assert.equal(statusLabel("failed"), "Failed");
});
