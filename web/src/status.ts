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

export type UploadField = "posting" | "cvs";

export interface UploadProblem {
  message: string;
  // The inputs to mark invalid. Empty for a wrong file type: the message names the file instead.
  fields: UploadField[];
}

// Checked in the order HR fixes things: a missing file first, then the posting, then the CVs.
export function uploadProblem(
  posting: { name: string } | null,
  cvs: { name: string }[],
): UploadProblem | null {
  if (posting === null || cvs.length === 0) {
    return { message: "Choose one posting PDF and at least one CV PDF.", fields: ["posting", "cvs"] };
  }
  const wrong = [posting, ...cvs].find((file) => !isPdfName(file.name));
  if (wrong !== undefined) {
    return { message: `${wrong.name} is not a PDF file.`, fields: [] };
  }
  return null;
}
