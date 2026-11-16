export interface Health {
  status: "ok" | "degraded";
  database: "reachable" | "unreachable";
}

function isHealth(value: unknown): value is Health {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const { status, database } = value as Record<string, unknown>;
  return (
    (status === "ok" || status === "degraded") &&
    (database === "reachable" || database === "unreachable")
  );
}

// The API answers 503 with the same JSON body when the database is down; that is data, not an error.
export async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  const body: unknown = await response.json();
  if (!isHealth(body)) {
    throw new Error(`unexpected health response (HTTP ${response.status})`);
  }
  return body;
}
