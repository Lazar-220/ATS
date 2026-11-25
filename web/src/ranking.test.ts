import assert from "node:assert/strict";
import { test } from "node:test";

import { failedMandatoryLabel, formatScore, sectionOf, sectionStarts, statusLabel, toCheck } from "./ranking.ts";

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

const meets = { status: "done", mandatory_failed: false } as const;
const misses = { status: "done", mandatory_failed: true } as const;
const failed = { status: "failed", mandatory_failed: false } as const;

test("a row belongs to one of three groups", () => {
  assert.equal(sectionOf(meets), "meets");
  assert.equal(sectionOf(misses), "misses");
  assert.equal(sectionOf(failed), "failed");
});

test("a section starts where the group changes", () => {
  assert.deepEqual(
    [...sectionStarts([meets, meets, misses, misses, failed])],
    [
      [0, "meets"],
      [2, "misses"],
      [4, "failed"],
    ],
  );
});

test("a group with no rows gets no header", () => {
  assert.deepEqual(
    [...sectionStarts([misses, failed])],
    [
      [0, "misses"],
      [1, "failed"],
    ],
  );
  assert.deepEqual([...sectionStarts([meets, failed])].map(([, section]) => section), ["meets", "failed"]);
  assert.deepEqual([...sectionStarts([meets])], [[0, "meets"]]);
  assert.deepEqual([...sectionStarts([])], []);
});

test("an interleaved order repeats a header and is never re-sorted", () => {
  const rows = [meets, misses, meets];
  assert.deepEqual(
    [...sectionStarts(rows)],
    [
      [0, "meets"],
      [1, "misses"],
      [2, "meets"],
    ],
  );
  assert.deepEqual(rows, [meets, misses, meets]);
});

function counts(flagged: number, unverified: number, listOnly: number) {
  return { flagged_verdicts: flagged, unverified_quote_verdicts: unverified, list_only_verdicts: listOnly };
}

test("an assessed row shows the total with its breakdown", () => {
  assert.deepEqual(toCheck({ status: "done", ...counts(3, 2, 1) }), {
    total: 3,
    tooltip: "2 quotes not verified, 1 only in the skills list",
  });
  assert.deepEqual(toCheck({ status: "done", ...counts(1, 1, 0) }), {
    total: 1,
    tooltip: "1 quote not verified, 0 only in the skills list",
  });
});

test("an assessed row with nothing to check still has its breakdown", () => {
  assert.deepEqual(toCheck({ status: "done", ...counts(0, 0, 0) }), {
    total: 0,
    tooltip: "0 quotes not verified, 0 only in the skills list",
  });
});

test("a failed row shows no total, even when an earlier run left flags", () => {
  assert.deepEqual(toCheck({ status: "failed", ...counts(2, 0, 0) }), { total: null, tooltip: null });
});
