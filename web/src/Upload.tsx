import { useId, useState, type FormEvent } from "react";

import type { RankingStatus } from "./api";
import { useRankingStatus, useUpload } from "./hooks";
import { href } from "./route";
import { documentLabel, documentNeedsAttention, requestLabel, uploadProblem, type UploadProblem } from "./status";
import { Button } from "./ui/Button";
import { FileField } from "./ui/FileField";
import { Icon } from "./ui/Icon";
import "./Upload.css";

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
                style={{ padding: "0.25rem", color: documentNeedsAttention(doc.status) ? "var(--color-error)" : undefined }}
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

export function UploadForm() {
  const [posting, setPosting] = useState<File | null>(null);
  const [cvs, setCvs] = useState<File[]>([]);
  const [problem, setProblem] = useState<UploadProblem | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const headingId = useId();
  const upload = useUpload();
  const status = useRankingStatus(requestId);

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = uploadProblem(posting, cvs);
    setProblem(found);
    if (found !== null || posting === null) {
      return;
    }
    upload.mutate(
      { posting, cvs },
      { onSuccess: (accepted) => setRequestId(accepted.request_id) },
    );
  }

  const busy = upload.isPending;
  // One message area: the first of these that is set.
  const formMessage =
    problem?.message ??
    (upload.isError ? upload.error.message : null) ??
    (requestId !== null && status.isError ? status.error.message : null);
  return (
    <section className="panel" aria-labelledby={headingId}>
      <h2 className="h2" id={headingId}>
        Upload
      </h2>
      <form onSubmit={submit}>
        <div className="upload-form">
          <FileField
            label="Job posting (PDF)"
            disabled={busy}
            invalid={problem?.fields.includes("posting") ?? false}
            onChange={(files) => setPosting(files[0] ?? null)}
          />
          <FileField
            label="CVs (PDF, one or more)"
            multiple
            disabled={busy}
            invalid={problem?.fields.includes("cvs") ?? false}
            onChange={setCvs}
          />
          <div>
            <Button type="submit" variant="primary" icon="upload" busy={busy} disabled={busy}>
              {busy ? "Uploading…" : "Upload and rank"}
            </Button>
          </div>
        </div>
      </form>
      <div id="form-msg" aria-live="polite">
        {formMessage !== null && (
          <div className="field-error">
            <Icon name="alert-circle" />
            <span>{formMessage}</span>
          </div>
        )}
      </div>
      {status.data && (
        <>
          <Progress status={status.data} />
          {status.data.status === "done" && (
            <p>
              <a href={href({ name: "ranking", positionId: status.data.position_id })}>
                Open the ranked list
              </a>
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
