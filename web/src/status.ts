import type { RankingStatus } from "./api";

// A request in one of these states will not change by itself, so polling can stop.
export function isSettled(status: RankingStatus["status"]): boolean {
  return status === "done" || status === "failed";
}
