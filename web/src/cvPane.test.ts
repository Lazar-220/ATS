import assert from "node:assert/strict";
import { test } from "node:test";

import { centredScrollTop, highlightRuns } from "./cvPane.ts";

const pane = { scrollTop: 0, paneTop: 100, paneHeight: 700 };

test("centredScrollTop puts the mark in the middle of the pane", () => {
  // The mark starts 1000 px below the top of the pane: 1000 - (700 - 20) / 2.
  assert.equal(centredScrollTop({ ...pane, markTop: 1100, markHeight: 20 }), 660);
});

test("centredScrollTop counts from where the pane is already scrolled", () => {
  assert.equal(centredScrollTop({ ...pane, scrollTop: 500, markTop: 600, markHeight: 20 }), 660);
  // A mark above the visible area scrolls back up.
  assert.equal(centredScrollTop({ ...pane, scrollTop: 900, markTop: 0, markHeight: 20 }), 460);
});

test("centredScrollTop never goes above the start of the text", () => {
  assert.equal(centredScrollTop({ ...pane, markTop: 150, markHeight: 20 }), 0);
});

test("centredScrollTop shows the start of a mark taller than the pane", () => {
  assert.equal(centredScrollTop({ ...pane, markTop: 1100, markHeight: 900 }), 1000);
});

test("highlightRuns joins neighbours of one level and gives an overlap the selected style", () => {
  const segments = [
    { text: "0", ids: [] },
    { text: "123", ids: ["a"] },
    { text: "45", ids: ["a", "b"] },
    { text: "678", ids: ["b"] },
    { text: "9", ids: [] },
  ];
  assert.deepEqual(highlightRuns(segments, null), [
    { text: "0", level: 0 },
    { text: "12345678", level: 1 },
    { text: "9", level: 0 },
  ]);
  assert.deepEqual(highlightRuns(segments, "a"), [
    { text: "0", level: 0 },
    { text: "12345", level: 2 },
    { text: "678", level: 1 },
    { text: "9", level: 0 },
  ]);
  assert.deepEqual(highlightRuns(segments, "b"), [
    { text: "0", level: 0 },
    { text: "123", level: 1 },
    { text: "45678", level: 2 },
    { text: "9", level: 0 },
  ]);
});
