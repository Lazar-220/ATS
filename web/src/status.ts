import type { RankingStatus } from "./api";

type RequestStatus = RankingStatus["status"];

// A request in one of these states will not change by itself, so polling can stop.
export function isSettled(status: RequestStatus): boolean {
  return status === "done" || status === "failed";
}

const REQUEST_LABEL: Record<RequestStatus, string> = {
  queued: "Waiting for the worker",
  running: "Processing",
  done: "Done",
  failed: "Failed",
};

export function requestLabel(status: RequestStatus): string {
  return REQUEST_LABEL[status];
}

// `status` is a free string in the API (uploaded, extracted, parsed, rejected, failed), so an
// unknown value is shown as it is rather than hidden.
const DOCUMENT_LABEL: Record<string, string> = {
  uploaded: "Waiting",
  extracted: "Text extracted",
  parsed: "Read",
  rejected: "Rejected",
  failed: "Failed",
};

export function documentLabel(status: string): string {
  return DOCUMENT_LABEL[status] ?? status;
}

export function documentNeedsAttention(status: string): boolean {
  return status === "rejected" || status === "failed";
}

// A file input accepts anything, so the form checks the extension before the API does.
export function isPdfName(name: string): boolean {
  return name.toLowerCase().endsWith(".pdf");
}
