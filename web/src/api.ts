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

export type Kind = "mandatory" | "nice_to_have";
export type SetupStatus = "pending" | "running" | "done" | "failed";

export interface Position {
  id: string;
  filename: string | null;
  rubric_status: "unconfirmed" | "confirmed";
  rubric_version: number;
  created_at: string;
  requirement_count: number;
  setup_status: SetupStatus;
  setup_message: string | null;
}

export interface RequirementRow {
  id: string;
  parent_id: string | null;
  text: string;
  kind: Kind;
  weight: number;
  min_months: number | null;
}

export interface PositionDetail extends Position {
  requirements: RequirementRow[];
}

// Requirement as sent in an edit. `id` and `parent` are labels inside the list, not database ids.
export interface RequirementPayload {
  id: number;
  text: string;
  kind: Kind;
  weight: number;
  min_months: number | null;
  parent: number | null;
}

export type AnswerRequest =
  | { type: "confirm"; position_id: string; dedup_key: string; rubric_version: number }
  | {
      type: "edit";
      position_id: string;
      dedup_key: string;
      rubric_version: number;
      requirements: { requirements: RequirementPayload[] };
    };

export interface AnswerResult {
  position_id: string;
  rubric_version: number;
  rubric_status: "unconfirmed" | "confirmed";
  rejudge_jobs: number;
  duplicate: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function nullable(check: (v: unknown) => boolean): (v: unknown) => boolean {
  return (v) => v === null || check(v);
}

const isString = (v: unknown): boolean => typeof v === "string";
const isNumber = (v: unknown): boolean => typeof v === "number";

function isPosition(value: unknown): value is Position {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isString(value["id"]) &&
    nullable(isString)(value["filename"]) &&
    (value["rubric_status"] === "unconfirmed" || value["rubric_status"] === "confirmed") &&
    isNumber(value["rubric_version"]) &&
    isString(value["created_at"]) &&
    isNumber(value["requirement_count"]) &&
    ["pending", "running", "done", "failed"].includes(String(value["setup_status"])) &&
    nullable(isString)(value["setup_message"])
  );
}

function isRequirementRow(value: unknown): value is RequirementRow {
  return (
    isRecord(value) &&
    isString(value["id"]) &&
    nullable(isString)(value["parent_id"]) &&
    isString(value["text"]) &&
    (value["kind"] === "mandatory" || value["kind"] === "nice_to_have") &&
    isNumber(value["weight"]) &&
    nullable(isNumber)(value["min_months"])
  );
}

function isPositionDetail(value: unknown): value is PositionDetail {
  return (
    isPosition(value) &&
    Array.isArray((value as unknown as Record<string, unknown>)["requirements"]) &&
    ((value as unknown as Record<string, unknown[]>)["requirements"] ?? []).every(isRequirementRow)
  );
}

function isAnswerResult(value: unknown): value is AnswerResult {
  return (
    isRecord(value) &&
    isString(value["position_id"]) &&
    isNumber(value["rubric_version"]) &&
    (value["rubric_status"] === "unconfirmed" || value["rubric_status"] === "confirmed") &&
    isNumber(value["rejudge_jobs"]) &&
    typeof value["duplicate"] === "boolean"
  );
}

// FastAPI sends `detail` as a string, or as a list of {loc, msg} for a request that fails validation.
function describeError(body: unknown, status: number): string {
  if (isRecord(body)) {
    const detail = body["detail"];
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item: unknown) => (isRecord(item) && isString(item["msg"]) ? String(item["msg"]) : ""))
        .filter((message) => message !== "")
        .join("; ");
    }
  }
  return `request failed (HTTP ${status})`;
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`/api${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(describeError(body, response.status));
  }
  return body;
}

export async function fetchPositions(): Promise<Position[]> {
  const body = await request("/positions");
  if (!Array.isArray(body) || !body.every(isPosition)) {
    throw new Error("unexpected positions response");
  }
  return body;
}

export async function fetchPosition(id: string): Promise<PositionDetail> {
  const body = await request(`/positions/${id}`);
  if (!isPositionDetail(body)) {
    throw new Error("unexpected position response");
  }
  return body;
}

export async function postAnswer(answer: AnswerRequest): Promise<AnswerResult> {
  const body = await request("/hr/answers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(answer),
  });
  if (!isAnswerResult(body)) {
    throw new Error("unexpected answer response");
  }
  return body;
}
