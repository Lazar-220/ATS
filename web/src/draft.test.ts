import assert from "node:assert/strict";
import { test } from "node:test";

import { removeRow, validate, validateDetail, type DraftRow } from "./draft.ts";

function row(key: string, patch: Partial<DraftRow> = {}): DraftRow {
  return { key, text: `Skill ${key}`, kind: "mandatory", weight: "1", minMonths: "", parentKey: null, ...patch };
}

function expectProblem(rows: DraftRow[], message: string, index: number | null, field: string | null) {
  assert.deepEqual(validateDetail(rows), { message, index, field });
  assert.equal(validate(rows), message);
}

test("valid rows have no problem", () => {
  const rows = [row("a", { weight: "5", minMonths: "36" }), row("b", { parentKey: "a", weight: " 3 " })];
  assert.equal(validateDetail(rows), null);
  assert.equal(validate(rows), null);
});

test("an empty list is a problem with no row or field", () => {
  expectProblem([], "Add at least one requirement.", null, null);
});

test("a blank text marks the text of that row", () => {
  expectProblem([row("a"), row("b", { text: "  " })], "Requirement 2 has no text.", 1, "text");
});

test("a weight outside 1 to 5 or not a whole number marks the weight", () => {
  const message = "Requirement 1: weight must be a whole number from 1 to 5.";
  for (const weight of ["", "0", "6", "2.5", "-1", "abc"]) {
    expectProblem([row("a", { weight })], message, 0, "weight");
  }
});

test("minimum months below 1 or not a whole number marks that field, and empty is allowed", () => {
  const message = "Requirement 1: minimum months must be a whole number of at least 1, or empty.";
  for (const minMonths of ["0", "1.5", "-3", "x"]) {
    expectProblem([row("a", { minMonths })], message, 0, "minMonths");
  }
  assert.equal(validate([row("a", { minMonths: "  " })]), null);
});

test("a loop marks the parent of the first row that is part of it", () => {
  // Row a only hangs below the loop of b and c, so b is the first row to fix.
  const rows = [row("a", { parentKey: "b" }), row("b", { parentKey: "c" }), row("c", { parentKey: "b" })];
  expectProblem(rows, "The parent links form a loop.", 1, "parentKey");
});

test("a row that is its own parent is a loop", () => {
  expectProblem([row("a", { parentKey: "a" })], "The parent links form a loop.", 0, "parentKey");
});

test("the first row with a problem wins, and field problems come before a loop", () => {
  expectProblem(
    [row("a", { weight: "9" }), row("b", { text: "" })],
    "Requirement 1: weight must be a whole number from 1 to 5.",
    0,
    "weight",
  );
  expectProblem(
    [row("a", { parentKey: "a" }), row("b", { text: "" })],
    "Requirement 2 has no text.",
    1,
    "text",
  );
});

test("removing a row resets the parent of its children only", () => {
  const rows = [row("a"), row("b", { parentKey: "a" }), row("c", { parentKey: "b" })];
  assert.deepEqual(
    removeRow(rows, "a").map((r) => [r.key, r.parentKey]),
    [
      ["b", null],
      ["c", "b"],
    ],
  );
});
