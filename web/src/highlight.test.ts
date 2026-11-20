import assert from "node:assert/strict";
import { test } from "node:test";

import { quoteState, segment, toRanges } from "./highlight.ts";

// Python's text[start:end] over code points, the reference the API's offsets come from.
function pythonSlice(text: string, start: number, end: number): string {
  return Array.from(text).slice(start, end).join("");
}

function highlighted(text: string, start: number, end: number): string {
  const ranges = toRanges(text, [{ id: "a", char_start: start, char_end: end }]);
  return segment(text, ranges)
    .filter((s) => s.ids.includes("a"))
    .map((s) => s.text)
    .join("");
}

test("segments always concatenate back to the exact text", () => {
  const text = "Alpha\r\nBeta \u{1F600} gamma";
  const ranges = toRanges(text, [
    { id: "a", char_start: 2, char_end: 9 },
    { id: "b", char_start: 6, char_end: 12 },
  ]);
  assert.equal(
    segment(text, ranges)
      .map((s) => s.text)
      .join(""),
    text,
  );
});

test("a quote at the very start and at the very end of the text", () => {
  assert.equal(highlighted("Java developer", 0, 4), "Java");
  assert.equal(highlighted("Java developer", 5, 14), "developer");
});

test("an emoji before the quote shifts UTF-16 indices but not the code point offsets", () => {
  const text = "Skills \u{1F680}\u{1F680} then Java and SQL";
  const start = Array.from(text).indexOf("J");
  assert.equal(pythonSlice(text, start, start + 4), "Java");
  assert.notEqual(text.slice(start, start + 4), "Java"); // the naive slice is wrong
  assert.equal(highlighted(text, start, start + 4), "Java");
});

test("a quote that itself contains an emoji", () => {
  const text = "x \u{1F600}ok\u{1F600} y";
  assert.equal(highlighted(text, 2, 6), "\u{1F600}ok\u{1F600}");
});

test("Cyrillic text and combining characters count code points, as Python does", () => {
  const cyrillic = "Искуство: Јава и SQL";
  assert.equal(highlighted(cyrillic, 10, 14), "Јава");
  // "e" + combining acute is two code points, so the offsets count the mark.
  const combining = "café Python";
  assert.equal(highlighted(combining, 6, 12), "Python");
});

test("CRLF line endings are kept and counted, not normalized", () => {
  const text = "Line one\r\nLine two Java\r\nend";
  const start = text.indexOf("Java");
  assert.equal(highlighted(text, start, start + 4), "Java");
  assert.equal(
    segment(text, [])
      .map((s) => s.text)
      .join(""),
    text,
  );
});

test("out-of-range, reversed, empty and fractional evidence is dropped, not clamped", () => {
  const text = "short";
  for (const [start, end] of [
    [0, 99],
    [-1, 3],
    [3, 3],
    [4, 2],
    [0.5, 2],
  ] as const) {
    assert.deepEqual(toRanges(text, [{ id: "a", char_start: start, char_end: end }]), []);
  }
  // One past the last character is still the end of the text, not out of range.
  assert.equal(highlighted(text, 0, 5), "short");
});

test("overlapping evidence yields segments that name every range covering them", () => {
  const text = "0123456789";
  const ranges = toRanges(text, [
    { id: "a", char_start: 1, char_end: 6 },
    { id: "b", char_start: 4, char_end: 9 },
  ]);
  const parts = segment(text, ranges).map((s) => [s.text, s.ids.join("+")]);
  assert.deepEqual(parts, [
    ["0", ""],
    ["123", "a"],
    ["45", "a+b"],
    ["678", "b"],
    ["9", ""],
  ]);
});

test("CV text with markup stays plain strings", () => {
  const text = "<script>alert(1)</script> <img src=x onerror=alert(2)> &amp; &lt;b&gt; Java";
  const start = Array.from(text).length - 4;
  const parts = segment(text, toRanges(text, [{ id: "a", char_start: start, char_end: start + 4 }]));
  assert.ok(parts.every((p) => typeof p.text === "string"));
  assert.equal(parts.map((p) => p.text).join(""), text); // entities are not decoded
  assert.equal(highlighted(text, start, start + 4), "Java");
});

test("a verdict with a failed quote is unverified and carries no highlight", () => {
  const flagged = {
    verdict: "met" as const,
    evidence: null,
    flags: [{ code: "quote_not_found", detail: "" }],
  };
  assert.equal(quoteState(flagged), "unverified");
  assert.equal(quoteState({ ...flagged, flags: [{ code: "no_evidence", detail: "" }] }), "unverified");
  assert.equal(quoteState({ verdict: "not_met", evidence: null, flags: [] }), "none");
  const evidence = { quote: "Java", char_start: 0, char_end: 4 };
  assert.equal(quoteState({ verdict: "met", evidence, flags: [] }), "verified");
});
