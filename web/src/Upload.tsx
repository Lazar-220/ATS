import { useState, type FormEvent } from "react";

import type { RankingStatus } from "./api";
import { useRankingStatus, useUpload } from "./hooks";
import { documentLabel, documentNeedsAttention, isPdfName, requestLabel } from "./status";

function Progress({ status }: { status: RankingStatus }) {
  return (
    <section aria-live="polite">
      <p data-testid="request-status">
        Status: <strong>{requestLabel(status.status)}</strong>
      </p>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            {["File", "Kind", "State", "Message"].map((title) => (
              <th key={title} style={{ textAlign: "left", padding: "0.25rem" }}>
                {title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {status.documents.map((doc) => (
            <tr key={doc.document_id}>
              <td style={{ padding: "0.25rem" }}>{doc.filename ?? doc.document_id}</td>
              <td style={{ padding: "0.25rem" }}>{doc.kind === "cv" ? "CV" : "Posting"}</td>
              <td style={{ padding: "0.25rem" }}>{documentLabel(doc.status)}</td>
              <td
                style={{ padding: "0.25rem", color: documentNeedsAttention(doc.status) ? "#b00020" : undefined }}
              >
                {doc.message}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function UploadForm({ onOpenRanking }: { onOpenRanking: (positionId: string) => void }) {
  const [posting, setPosting] = useState<File | null>(null);
  const [cvs, setCvs] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const upload = useUpload();
  const status = useRankingStatus(requestId);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (posting === null || cvs.length === 0) {
      setProblem("Choose one posting PDF and at least one CV PDF.");
      return;
    }
    const wrong = [posting, ...cvs].find((file) => !isPdfName(file.name));
    if (wrong !== undefined) {
      setProblem(`${wrong.name} is not a PDF file.`);
      return;
    }
    setProblem(null);
    upload.mutate(
      { posting, cvs },
      { onSuccess: (accepted) => setRequestId(accepted.request_id) },
    );
  }

  const busy = upload.isPending;
  return (
    <section>
      <h2>Upload</h2>
      <form onSubmit={submit}>
        <p>
          <label>
            Job posting (PDF){" "}
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              onChange={(event) => setPosting(event.target.files?.[0] ?? null)}
            />
          </label>
        </p>
        <p>
          <label>
            CVs (PDF, one or more){" "}
            <input
              type="file"
              accept="application/pdf,.pdf"
              multiple
              disabled={busy}
              onChange={(event) => setCvs(Array.from(event.target.files ?? []))}
            />
          </label>
        </p>
        <button type="submit" disabled={busy}>
          {busy ? "Uploading…" : "Upload and rank"}
        </button>
      </form>
      {problem !== null && <p role="alert">{problem}</p>}
      {upload.isError && <p role="alert">{upload.error.message}</p>}
      {requestId !== null && status.isError && <p role="alert">{status.error.message}</p>}
      {status.data && (
        <>
          <Progress status={status.data} />
          {status.data.status === "done" && (
            <p>
              <button type="button" onClick={() => onOpenRanking(status.data.position_id)}>
                Open the ranked list
              </button>
            </p>
          )}
          {status.data.status === "failed" && (
            <p role="alert">The posting could not be read, so there is nothing to rank against.</p>
          )}
        </>
      )}
    </section>
  );
}
