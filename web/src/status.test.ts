import assert from "node:assert/strict";
import { test } from "node:test";

import { documentLabel, documentNeedsAttention, isPdfName, isSettled, requestLabel } from "./status.ts";

test("polling stops only for done and failed", () => {
  assert.equal(isSettled("done"), true);
  assert.equal(isSettled("failed"), true);
  assert.equal(isSettled("queued"), false);
  assert.equal(isSettled("running"), false);
});

test("request and document states have labels, and an unknown document state is shown as is", () => {
  assert.equal(requestLabel("queued"), "Waiting for the worker");
  assert.equal(documentLabel("rejected"), "Rejected");
  assert.equal(documentLabel("something_new"), "something_new");
});

test("only rejected and failed documents need attention", () => {
  assert.equal(documentNeedsAttention("rejected"), true);
  assert.equal(documentNeedsAttention("failed"), true);
  assert.equal(documentNeedsAttention("parsed"), false);
});

test("the PDF check looks at the extension, in any case", () => {
  assert.equal(isPdfName("cv.PDF"), true);
  assert.equal(isPdfName("cv.pdf.exe"), false);
  assert.equal(isPdfName("cv"), false);
});
