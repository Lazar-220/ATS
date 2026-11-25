import type { Health } from "./api";

export type HealthState = "checking" | "ok" | "degraded" | "unreachable";

// The API answers 503 with a normal body when the database is down, and fetchHealth returns it as
// data. So `degraded` is read from the body, while `unreachable` means no usable answer at all.
export function healthState(query: {
  isPending: boolean;
  isError: boolean;
  data: Health | undefined;
}): HealthState {
  if (query.isError) {
    return "unreachable";
  }
  if (query.isPending || query.data === undefined) {
    return "checking";
  }
  return query.data.status === "ok" && query.data.database === "reachable" ? "ok" : "degraded";
}
