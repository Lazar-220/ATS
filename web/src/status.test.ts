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

import { uploadProblem } from "./status.ts";

const PICK = "Choose one posting PDF and at least one CV PDF.";

test("uploadProblem asks for a posting and a CV, and marks both fields", () => {
  const expected = { message: PICK, fields: ["posting", "cvs"] };
  assert.deepEqual(uploadProblem(null, [{ name: "a.pdf" }]), expected);
  assert.deepEqual(uploadProblem({ name: "p.pdf" }, []), expected);
  assert.deepEqual(uploadProblem(null, []), expected);
});

test("uploadProblem names the first file that is not a PDF and marks no field", () => {
  assert.deepEqual(uploadProblem({ name: "p.docx" }, [{ name: "a.pdf" }]), {
    message: "p.docx is not a PDF file.",
    fields: [],
  });
  assert.deepEqual(uploadProblem({ name: "p.pdf" }, [{ name: "a.pdf" }, { name: "b.txt" }, { name: "c.png" }]), {
    message: "b.txt is not a PDF file.",
    fields: [],
  });
});

test("uploadProblem returns null when every file is a PDF", () => {
  assert.equal(uploadProblem({ name: "P.PDF" }, [{ name: "a.pdf" }, { name: "b.pdf" }]), null);
});
