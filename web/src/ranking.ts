import type { RankingRow } from "./api";

export function formatScore(row: Pick<RankingRow, "status" | "score">): string {
  // A failed assessment has no score; showing 0 would rank it as a weak candidate.
  if (row.status === "failed" || row.score === null) {
    return "–";
  }
  return row.score.toFixed(1);
}

export function statusLabel(status: RankingRow["status"]): string {
  return status === "done" ? "Assessed" : "Failed";
}

// Columns say yes or no in words, so the table reads without colour.
export function failedMandatoryLabel(row: Pick<RankingRow, "status" | "mandatory_failed">): string {
  if (row.status === "failed") {
    return "–";
  }
  return row.mandatory_failed ? "Mandatory requirement not met" : "No";
}

// The groups the server's order puts the rows in.
export type Section = "meets" | "misses" | "failed";

export const SECTION_LABEL: Record<Section, string> = {
  meets: "Meets every mandatory requirement",
  misses: "Misses a mandatory requirement",
  failed: "Could not be assessed",
};

export function sectionOf(row: Pick<RankingRow, "status" | "mandatory_failed">): Section {
  if (row.status === "failed") {
    return "failed";
  }
  return row.mandatory_failed ? "misses" : "meets";
}

// The index of every row that opens a group, in the order the server sent. The rows are never
// re-sorted here: if a group ever came back twice, it would get two headers.
export function sectionStarts(rows: Pick<RankingRow, "status" | "mandatory_failed">[]): Map<number, Section> {
  const starts = new Map<number, Section>();
  let previous: Section | null = null;
  rows.forEach((row, index) => {
    const section = sectionOf(row);
    if (section !== previous) {
      starts.set(index, section);
      previous = section;
    }
  });
  return starts;
}

export interface ToCheck {
  // Null on a failed row: its verdicts, if any are left, describe no result.
  total: number | null;
  // The breakdown of an assessed row. The total can be larger than its two parts together.
  tooltip: string | null;
}

export function toCheck(
  row: Pick<RankingRow, "status" | "flagged_verdicts" | "unverified_quote_verdicts" | "list_only_verdicts">,
): ToCheck {
  if (row.status === "failed") {
    return { total: null, tooltip: null };
  }
  const unverified = row.unverified_quote_verdicts;
  const noun = unverified === 1 ? "quote" : "quotes";
  return {
    total: row.flagged_verdicts,
    tooltip: `${unverified} ${noun} not verified, ${row.list_only_verdicts} only in the skills list`,
  };
}
