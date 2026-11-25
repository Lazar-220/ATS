import type { Flag } from "./api";

// What a flag note says: a title for HR, the code as small print, and an explanation.
export interface FlagText {
  title: string;
  // Null when the title already is the code.
  code: string | null;
  // Null when there is nothing to add.
  body: string | null;
}

// Flags of the CV document. The sentences are the screen's own.
const CV_FLAGS = new Map<string, { title: string; body: string }>([
  [
    "low_coverage",
    {
      title: "Partly read",
      body: "Parts of this CV could not be read into structured data, so the facts may be incomplete.",
    },
  ],
  [
    "suspected_injection",
    {
      title: "Text aimed at an AI screener",
      body: "This CV contains text that looks aimed at an automated screener. Read it with care.",
    },
  ],
  [
    "hidden_text",
    {
      title: "Hidden text removed",
      body: "Hidden text (white, tiny, off-page or covered) was found in the PDF and left out of the assessment.",
    },
  ],
  [
    "invisible_characters",
    {
      title: "Invisible characters removed",
      body: "Invisible characters were found in the CV text and removed before the assessment.",
    },
  ],
  [
    "mixed_script_words",
    {
      title: "Mixed Cyrillic and Latin letters",
      body: "Some words mix Cyrillic and Latin letters, which can be an attempt to disguise text.",
    },
  ],
]);

// Flags of one verdict. Their explanation is the `detail` the API sends.
const VERDICT_FLAG_TITLES = new Map<string, string>([
  ["quote_not_found", "Quote not verified"],
  ["no_evidence", "No quote given"],
  ["list_only_skill", "Only in the skills list"],
]);

export function cvFlagText(code: string): FlagText {
  const known = CV_FLAGS.get(code);
  return known === undefined ? { title: code, code: null, body: null } : { ...known, code };
}

export function verdictFlagText(flag: Flag): FlagText {
  const title = VERDICT_FLAG_TITLES.get(flag.code);
  const body = flag.detail === "" ? null : flag.detail;
  return title === undefined ? { title: flag.code, code: null, body } : { title, code: flag.code, body };
}
