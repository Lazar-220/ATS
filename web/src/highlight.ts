import type { Verdict } from "./api";

// The API's offsets are Python string indices, that is Unicode code points into `cv_text`.
// JavaScript indexes strings by UTF-16 code unit, so a character outside the BMP (an emoji, some
// CJK) counts as 2 here and as 1 there. Slicing with the raw offsets would shift every highlight
// after the first such character, so offsets are converted first. `cv_text` is never trimmed,
// normalized or re-encoded: any change would move the characters the offsets point at.

export interface Range {
  id: string;
  // UTF-16 indices into the text, end exclusive.
  start: number;
  end: number;
}

export interface Segment {
  text: string;
  // Ids of every evidence range that covers this stretch of text (ranges may overlap).
  ids: string[];
}

export interface Evidence {
  id: string;
  char_start: number;
  char_end: number;
}

function isHighSurrogate(unit: number): boolean {
  return unit >= 0xd800 && unit <= 0xdbff;
}

// Walks the text once and returns, for each requested code point offset, its UTF-16 index.
// An offset past the end of the text maps to null.
function toUtf16(text: string, offsets: number[]): Map<number, number | null> {
  const wanted = new Set(offsets);
  const result = new Map<number, number | null>();
  let codePoint = 0;
  let unit = 0;
  while (unit <= text.length) {
    if (wanted.has(codePoint)) {
      result.set(codePoint, unit);
    }
    if (unit === text.length) {
      break;
    }
    unit += isHighSurrogate(text.charCodeAt(unit)) && unit + 1 < text.length ? 2 : 1;
    codePoint += 1;
  }
  for (const offset of wanted) {
    if (!result.has(offset)) {
      result.set(offset, null);
    }
  }
  return result;
}

// Evidence that does not point inside the text (negative, reversed, empty, fractional or past the
// end) is dropped rather than clamped: a wrong highlight misleads more than none does.
export function toRanges(text: string, evidence: Evidence[]): Range[] {
  const usable = evidence.filter(
    (e) =>
      Number.isInteger(e.char_start) &&
      Number.isInteger(e.char_end) &&
      e.char_start >= 0 &&
      e.char_end > e.char_start,
  );
  const map = toUtf16(
    text,
    usable.flatMap((e) => [e.char_start, e.char_end]),
  );
  const ranges: Range[] = [];
  for (const e of usable) {
    const start = map.get(e.char_start);
    const end = map.get(e.char_end);
    if (start != null && end != null) {
      ranges.push({ id: e.id, start, end });
    }
  }
  return ranges;
}

// Splits the text at every range boundary. Concatenating the segments gives back the text
// exactly, and every segment is a plain string for React to render as text.
export function segment(text: string, ranges: Range[]): Segment[] {
  const cuts = new Set<number>([0, text.length]);
  for (const r of ranges) {
    cuts.add(r.start);
    cuts.add(r.end);
  }
  const points = [...cuts].filter((p) => p >= 0 && p <= text.length).sort((a, b) => a - b);
  const segments: Segment[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const from = points[i] ?? 0;
    const to = points[i + 1] ?? text.length;
    if (to > from) {
      const ids = ranges.filter((r) => r.start <= from && r.end >= to).map((r) => r.id);
      segments.push({ text: text.slice(from, to), ids });
    }
  }
  return segments;
}

export type QuoteState = "verified" | "unverified" | "none";

// `verified`: code found the quote in the CV, so it can be highlighted. `unverified`: the judge
// gave a verdict that needs a quote and the check failed or none was given; nothing is
// highlighted. `none`: not_met, no quote expected.
export function quoteState(verdict: Pick<Verdict, "verdict" | "evidence" | "flags">): QuoteState {
  if (verdict.evidence !== null) {
    return "verified";
  }
  const flagged = verdict.flags.some((f) => f.code === "quote_not_found" || f.code === "no_evidence");
  if (flagged && verdict.verdict !== "not_met") {
    return "unverified";
  }
  return "none";
}
