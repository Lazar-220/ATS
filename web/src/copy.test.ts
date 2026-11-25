import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { sourceFiles } from "./sourceFiles.ts";

// The user-facing texts of the screens (docs/review/frontend-plan.md, Appendix A), pinned so that a
// restyle cannot drop or reword one by accident. A phase that is allowed to change a text edits
// this list in the same commit, so the change is visible in review.
//
// A string without whitespace must appear whole, as a quoted literal or as a JSX text node:
// single words such as "State" or "Upload" also occur inside identifiers (useState, UploadForm),
// so a substring match would still pass after the text had left the screen. A string with
// whitespace is specific enough to be matched as a substring.
const SHELL = [
  "ATS",
  "Checking the API…",
  "API unreachable: ",
  "API: ",
  ", database: ",
  "Positions",
  "Ranked list",
  "There is no such page.",
  "Try again",
  "Loading…",
];

const HOME = [
  "Upload",
  "Job posting (PDF)",
  "CVs (PDF, one or more)",
  "Upload and rank",
  "Uploading…",
  "Choose one posting PDF and at least one CV PDF.",
  " is not a PDF file.",
  "Status: ",
  "File",
  "Kind",
  "State",
  "Message",
  "CV",
  "Posting",
  "Open the ranked list",
  "The posting could not be read, so there is nothing to rank against.",
  "Waiting for the worker",
  "Processing",
  "Done",
  "Failed",
  "Waiting",
  "Text extracted",
  "Read",
  "Rejected",
  "Rubric",
  "Version",
  "Requirements",
  "waiting for the posting text",
  "extracting requirements…",
  "failed",
  "No positions yet. Upload a posting and CVs above to create one.",
];

const REQUIREMENTS = [
  "Position",
  "Rubric ",
  ", version ",
  " — scores for this position carry the label “rubric unconfirmed” until you confirm.",
  "Extracting the requirements from the posting…",
  "#",
  "Requirement",
  "Type",
  "Weight (1–5)",
  "Minimum months",
  "Parent",
  "Mandatory",
  "Nice to have",
  "None",
  "(empty)",
  "Add requirement",
  "Save changes",
  "Confirm requirements",
  "Discard changes",
  "Save your changes first, then confirm",
  "Saved.",
  "Already saved.",
  "Add at least one requirement.",
  " has no text.",
  ": weight must be a whole number from ",
  ": minimum months must be a whole number of at least 1, or empty.",
  "The parent links form a loop.",
];

const RANKING = [
  "No CV has been assessed yet. Results appear here as the worker finishes each CV; if you just uploaded, give it a moment.",
  "The requirements are not confirmed yet, so these scores are provisional. Confirm or edit them on the requirements screen.",
  "Candidate",
  "Score",
  "Failed mandatory",
  "Assessment",
  "Check verdicts",
  "(name not found)",
  "Assessed",
  "Mandatory requirement not met",
  "No",
  "–",
];

const ASSESSMENT = [
  "Met",
  "Partial",
  "Not met",
  "Verdict: ",
  "quote found in the CV",
  "Unverified: the quote could not be found in the CV, so nothing is highlighted",
  "mandatory",
  "nice to have",
  ", weight ",
  ", minimum ",
  " months",
  " · score ",
  " · a mandatory requirement is not met",
  " months of experience",
  "This CV could not be assessed",
  "This assessment has no verdicts.",
  "The CV text is not available.",
  "rubric unconfirmed",
  "Parts of this CV could not be read into structured data, so the facts may be incomplete.",
  "This CV contains text that looks aimed at an automated screener. Read it with care.",
  "Hidden text (white, tiny, off-page or covered) was found in the PDF and left out of the assessment.",
  "Invisible characters were found in the CV text and removed before the assessment.",
  "Some words mix Cyrillic and Latin letters, which can be an attempt to disguise text.",
];

const PINNED_TEXTS = [...SHELL, ...HOME, ...REQUIREMENTS, ...RANKING, ...ASSESSMENT];

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// The whole word as a string literal, or as a JSX text node with only whitespace around it.
function appearsWhole(word: string, source: string): boolean {
  const body = escapeRegExp(word);
  return new RegExp(`(["'\`])${body}\\1|>\\s*${body}\\s*<`).test(source);
}

// JSX renders a line break with its indentation, and {" "}, as one space, so a sentence wrapped in
// the source is still the same sentence on the screen.
function asRendered(source: string): string {
  return source.replaceAll('{" "}', " ").replace(/\s+/g, " ");
}

function isPinned(text: string, source: string): boolean {
  return /\s/.test(text) ? asRendered(source).includes(text) : appearsWhole(text, source);
}

test("the list is the full set of Appendix A", () => {
  assert.equal(PINNED_TEXTS.length, 103);
  assert.equal(new Set(PINNED_TEXTS).size, PINNED_TEXTS.length);
});

test("a single word must stand alone, not inside an identifier", () => {
  assert.ok(appearsWhole("State", `const header = "State";`));
  assert.ok(appearsWhole("State", `<th>State</th>`));
  assert.ok(appearsWhole("State", `<th>\n  State\n</th>`));
  assert.ok(!appearsWhole("State", `const [open, setOpen] = useState(false); type DocumentState = string;`));
});

test("every pinned text appears in the app's sources", () => {
  const dir = new URL(".", import.meta.url);
  const sources = sourceFiles().map((name) => readFileSync(new URL(name, dir), "utf8"));
  assert.ok(sources.length > 0);
  const missing = PINNED_TEXTS.filter((text) => !sources.some((source) => isPinned(text, source)));
  assert.deepEqual(missing, []);
});
