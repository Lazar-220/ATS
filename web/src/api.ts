import type { components } from "./api-types";

// Types come from the API's OpenAPI schema (`make api-types`); nothing here is written by hand.
type Schemas = components["schemas"];

export type Health = Schemas["Health"];
export type Position = Schemas["PositionOut"];
export type PositionDetail = Schemas["PositionDetailOut"];
export type RequirementRow = Schemas["RequirementOut"];
export type RequirementPayload = Schemas["RequirementDraft"];
export type Kind = RequirementRow["kind"];
export type SetupStatus = Position["setup_status"];
export type AnswerRequest = Schemas["ConfirmAnswer"] | Schemas["EditAnswer"];
export type AnswerResult = Schemas["AnswerOut"];
export type RankingAccepted = Schemas["RankingAccepted"];
export type RankingStatus = Schemas["RankingStatus"];
export type DocumentStatus = Schemas["DocumentStatus"];
export type PositionRanking = Schemas["PositionRankingOut"];
export type RankingRow = Schemas["RankingRowOut"];
export type Assessment = Schemas["AssessmentOut"];
export type Verdict = Schemas["VerdictOut"];
export type Evidence = Schemas["EvidenceOut"];
export type Flag = Schemas["FlagOut"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

// FastAPI sends `detail` as a string, or as a list of {loc, msg} for a request that fails validation.
export function describeError(body: unknown, status: number): string {
  if (isRecord(body)) {
    const detail = body["detail"];
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item: unknown) => (isRecord(item) && typeof item["msg"] === "string" ? item["msg"] : ""))
        .filter((message) => message !== "");
      if (messages.length > 0) {
        return messages.join("; ");
      }
    }
  }
  return `request failed (HTTP ${status})`;
}

// The generated types are the contract: the body is trusted to match them once the status is ok.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(describeError(body, response.status));
  }
  return body as T;
}

// The API answers 503 with the same JSON body when the database is down; that is data, not an error.
export async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  const body: unknown = await response.json().catch(() => null);
  if (!isRecord(body) || typeof body["status"] !== "string") {
    throw new Error(`unexpected health response (HTTP ${response.status})`);
  }
  return body as Health;
}

export const fetchPositions = () => request<Position[]>("/positions");
export const fetchPosition = (id: string) => request<PositionDetail>(`/positions/${id}`);
export const fetchRankingStatus = (requestId: string) =>
  request<RankingStatus>(`/rankings/${requestId}`);
export const fetchPositionRanking = (positionId: string) =>
  request<PositionRanking>(`/positions/${positionId}/ranking`);
export const fetchAssessment = (assessmentId: string) =>
  request<Assessment>(`/assessments/${assessmentId}`);

export const postAnswer = (answer: AnswerRequest) =>
  request<AnswerResult>("/hr/answers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(answer),
  });

function cvForm(cvs: File[]): FormData {
  const form = new FormData();
  for (const cv of cvs) {
    form.append("cvs", cv);
  }
  return form;
}

// No Content-Type header on either upload: the browser sets the multipart boundary itself.
export function uploadRanking(posting: File, cvs: File[]): Promise<RankingAccepted> {
  const form = cvForm(cvs);
  form.append("posting", posting);
  return request<RankingAccepted>("/rankings", { method: "POST", body: form });
}

// The same request for a position that exists: the server uses its stored posting.
export function addCvs(positionId: string, cvs: File[]): Promise<RankingAccepted> {
  return request<RankingAccepted>(`/positions/${positionId}/cvs`, {
    method: "POST",
    body: cvForm(cvs),
  });
}
