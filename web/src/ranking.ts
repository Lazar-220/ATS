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
