import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { useId, useImperativeHandle, useRef, useState, type FormEvent, type Ref } from "react";

import type { Position, RankingAccepted, RankingStatus } from "./api";
import { useAddCvs, useRankingStatus, useUpload } from "./hooks";
import { href } from "./route";
import { documentRowVariant, uploadProblem, type UploadProblem } from "./status";
import { AddModeChip } from "./ui/AddModeChip";
import { Button } from "./ui/Button";
import { DocumentState } from "./ui/DocumentState";
import { FileField } from "./ui/FileField";
import { Icon } from "./ui/Icon";
import { Link } from "./ui/Link";
import { RequestStatus } from "./ui/RequestStatus";
import "./ui/Table.css";
import "./Upload.css";

type DocumentRow = RankingStatus["documents"][number];

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, DocumentRow>();

// Filenames and messages come from the uploaded files and the backend: they are rendered as
// text nodes only (§4.4).
const columns = helper.columns([
  helper.display({ id: "file", header: "File", cell: ({ row }) => row.original.filename ?? row.original.document_id }),
  helper.display({ id: "kind", header: "Kind", cell: ({ row }) => (row.original.kind === "cv" ? "CV" : "Posting") }),
  helper.display({ id: "state", header: "State", cell: ({ row }) => <DocumentState status={row.original.status} /> }),
  helper.display({
    id: "message",
    header: "Message",
    cell: ({ row }) => {
      const variant = documentRowVariant(row.original);
      if (row.original.message === null || variant === "default") {
        return null;
      }
      return (
        <span className={variant === "info" ? "msg msg--info" : "msg"}>
          <Icon name={variant === "info" ? "info" : "alert-circle"} />
          <span>{row.original.message}</span>
        </span>
      );
    },
  }),
]);

const ROW_CLASS = { attention: "row--attention", info: "row--info", default: undefined } as const;

function DocumentsTable({ documents }: { documents: DocumentRow[] }) {
  const table = useTable({ features, columns, data: documents });
  return (
    <div className="table-wrap">
      <table className="table" aria-label="Uploaded files">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id}>{header.isPlaceholder ? null : <table.FlexRender header={header} />}</th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.original.document_id} className={ROW_CLASS[documentRowVariant(row.original)]}>
              {row.getAllCells().map((cell) => (
                <td key={cell.id}>
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Progress({ status }: { status: RankingStatus }) {
  return (
    <div className="upload-progress">
      <RequestStatus status={status.status} />
      <DocumentsTable documents={status.documents} />
      {status.status === "done" && (
        <div>
          <Link href={href({ name: "ranking", positionId: status.position_id })} strong trailingIcon="arrow-right">
            Open the ranked list
          </Link>
        </div>
      )}
      {status.status === "failed" && (
        <div className="msg msg--primary" role="alert">
          <Icon name="alert-circle" />
          <span>The posting could not be read, so there is nothing to rank against.</span>
        </div>
      )}
    </div>
  );
}

export interface UploadFormHandle {
  addTo: (position: Position) => void;
}

export function UploadForm({ ref }: { ref?: Ref<UploadFormHandle> }) {
  const [posting, setPosting] = useState<File | null>(null);
  const [cvs, setCvs] = useState<File[]>([]);
  // The position that receives the CVs in add mode; null means a new posting is uploaded.
  const [target, setTarget] = useState<Position | null>(null);
  const [problem, setProblem] = useState<UploadProblem | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const headingId = useId();
  const cvInput = useRef<HTMLInputElement>(null);
  const upload = useUpload();
  const add = useAddCvs();
  const status = useRankingStatus(requestId);
  const busy = upload.isPending || add.isPending;

  // Entering or leaving add mode starts a clean form: no message and no earlier progress. The
  // posting is forgotten because its input is replaced and would come back empty.
  function switchTarget(next: Position | null) {
    setTarget(next);
    setPosting(null);
    setProblem(null);
    setRequestId(null);
    upload.reset();
    add.reset();
  }

  useImperativeHandle(ref, () => ({
    addTo(position) {
      // A request that is being sent belongs to the form as it is; it cannot be redirected.
      if (busy) {
        return;
      }
      switchTarget(position);
      // CVs chosen before were not chosen for this position.
      setCvs([]);
      if (cvInput.current !== null) {
        cvInput.current.value = "";
        // Focusing also scrolls the form into view from the positions table.
        cvInput.current.focus();
      }
    },
  }));

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = uploadProblem(posting, cvs, target !== null);
    setProblem(found);
    if (found !== null) {
      return;
    }
    const callbacks = { onSuccess: (accepted: RankingAccepted) => setRequestId(accepted.request_id) };
    if (target !== null) {
      add.mutate({ positionId: target.id, cvs }, callbacks);
    } else if (posting !== null) {
      upload.mutate({ posting, cvs }, callbacks);
    }
  }

  // One message area: the first of these that is set.
  const formMessage =
    problem?.message ??
    (upload.isError ? upload.error.message : null) ??
    (add.isError ? add.error.message : null) ??
    (requestId !== null && status.isError ? status.error.message : null);
  return (
    <section className="panel" aria-labelledby={headingId}>
      <h2 className="h2" id={headingId}>
        Upload
      </h2>
      <form onSubmit={submit}>
        <div className="upload-form">
          {target === null ? (
            <FileField
              label="Job posting (PDF)"
              disabled={busy}
              invalid={problem?.fields.includes("posting") ?? false}
              onChange={(files) => setPosting(files[0] ?? null)}
            />
          ) : (
            <AddModeChip filename={target.filename ?? target.id} disabled={busy} onLeave={() => switchTarget(null)} />
          )}
          <FileField
            ref={cvInput}
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
      {status.data && <Progress status={status.data} />}
    </section>
  );
}
