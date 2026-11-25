import assert from "node:assert/strict";
import { test } from "node:test";

import { cvFlagText, verdictFlagText } from "./flags.ts";

test("every CV flag has a title, its code and its sentence", () => {
  const titles = {
    low_coverage: "Partly read",
    suspected_injection: "Text aimed at an AI screener",
    hidden_text: "Hidden text removed",
    invisible_characters: "Invisible characters removed",
    mixed_script_words: "Mixed Cyrillic and Latin letters",
  };
  for (const [code, title] of Object.entries(titles)) {
    const text = cvFlagText(code);
    assert.equal(text.title, title);
    assert.equal(text.code, code);
    assert.ok(text.body !== null && text.body.length > 0);
  }
  assert.equal(
    cvFlagText("suspected_injection").body,
    "This CV contains text that looks aimed at an automated screener. Read it with care.",
  );
});

test("a verdict flag takes its explanation from the API's detail", () => {
  const titles = {
    quote_not_found: "Quote not verified",
    no_evidence: "No quote given",
    list_only_skill: "Only in the skills list",
  };
  for (const [code, title] of Object.entries(titles)) {
    assert.deepEqual(verdictFlagText({ code, detail: "why" }), { title, code, body: "why" });
  }
  assert.equal(verdictFlagText({ code: "no_evidence", detail: "" }).body, null);
});

test("an unknown code is the title", () => {
  assert.deepEqual(cvFlagText("new_flag"), { title: "new_flag", code: null, body: null });
  assert.deepEqual(verdictFlagText({ code: "new_flag", detail: "" }), { title: "new_flag", code: null, body: null });
  // A verdict flag's detail was always shown, so it stays for a code without a title.
  assert.deepEqual(verdictFlagText({ code: "new_flag", detail: "why" }), {
    title: "new_flag",
    code: null,
    body: "why",
  });
});

test("a code that is also an object property is still unknown", () => {
  assert.equal(cvFlagText("constructor").title, "constructor");
  assert.equal(verdictFlagText({ code: "toString", detail: "" }).title, "toString");
});
