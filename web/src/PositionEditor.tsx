import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  fetchPosition,
  postAnswer,
  type AnswerRequest,
  type PositionDetail,
} from "./api";
import { newRow, removeRow, toDraft, toPayload, validateDetail, type DraftRow } from "./draft";
import { href } from "./route";
import { RequirementsTable } from "./RequirementsTable";
import { Button } from "./ui/Button";
import { FieldError } from "./ui/FieldError";
import { Icon } from "./ui/Icon";
import { Link } from "./ui/Link";
import { Loading } from "./ui/Loading";
import { ErrorNotice } from "./ui/Notice";
import { SaveResult } from "./ui/SaveResult";
import { Tooltip } from "./ui/Tooltip";
import "./PositionEditor.css";

// Omit on each member of the union, so `type` still tells the two answers apart.
type WithoutKey<T> = T extends unknown ? Omit<T, "dedup_key"> : never;

function RequirementsForm({ position }: { position: PositionDetail }) {
  const queryClient = useQueryClient();
  const saved = toDraft(position.requirements);
  const [rows, setRows] = useState<DraftRow[]>(saved);
  // One key per intent: pressing the same button again with the same content repeats the
  // request, and the server recognizes it instead of doing the work twice.
  const attempt = useRef<{ signature: string; key: string } | null>(null);

  const answer = useMutation({
    mutationFn: postAnswer,
    // Also after a failure: a 409 means the screen is out of date, so load the current version.
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["position", position.id] }),
        queryClient.invalidateQueries({ queryKey: ["positions"] }),
      ]);
    },
  });

  const problem = validateDetail(rows);
  const dirty = JSON.stringify(rows) !== JSON.stringify(saved);
  // The message and the marked field appear only once there is something unsaved to fix.
  const shown = dirty ? problem : null;
  const busy = answer.isPending;
  const saving = busy && answer.variables.type === "edit";
  const confirming = busy && answer.variables.type === "confirm";
  const confirmDisabled =
    busy || dirty || position.rubric_status === "confirmed" || rows.length === 0;

  function send(body: WithoutKey<AnswerRequest>) {
    const signature = JSON.stringify(body);
    if (attempt.current?.signature !== signature) {
      attempt.current = { signature, key: crypto.randomUUID() };
    }
    answer.mutate({ ...body, dedup_key: attempt.current.key } as AnswerRequest);
  }

  function save() {
    send({
      type: "edit",
      position_id: position.id,
      rubric_version: position.rubric_version,
      requirements: { requirements: toPayload(rows) },
    });
  }

  function confirm() {
    send({ type: "confirm", position_id: position.id, rubric_version: position.rubric_version });
  }

  return (
    <div className="requirements-form">
      <RequirementsTable
        rows={rows}
        disabled={busy}
        problem={shown}
        update={(key, patch) =>
          setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)))
        }
        remove={(key) => setRows((current) => removeRow(current, key))}
        add={() => setRows((current) => [...current, newRow()])}
      />
      <div className="action-bar">
        <div className="action-bar__msg" aria-live="polite">
          {shown !== null && <FieldError message={shown.message} />}
          {answer.isError && <SaveResult kind="error" message={answer.error.message} />}
          {answer.isSuccess && !dirty && (
            <SaveResult kind={answer.data.duplicate ? "already" : "saved"} />
          )}
        </div>
        <div className="action-bar__btns">
          <Button
            variant="primary"
            busy={saving}
            disabled={busy || !dirty || problem !== null}
            onClick={save}
          >
            Save changes
          </Button>
          <Tooltip content={dirty ? "Save your changes first, then confirm" : null}>
            {(describedBy) => (
              // Not `disabled`: the button stays focusable so the tooltip can be reached.
              <Button
                variant={confirming || !confirmDisabled ? "primary" : "secondary"}
                busy={confirming}
                ariaDisabled={confirmDisabled && !confirming}
                aria-describedby={describedBy}
                onClick={() => {
                  if (!confirmDisabled) {
                    confirm();
                  }
                }}
              >
                Confirm requirements
              </Button>
            )}
          </Tooltip>
          {dirty && (
            <Button variant="ghost" disabled={busy} onClick={() => setRows(saved)}>
              Discard changes
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function RubricLine({ position }: { position: PositionDetail }) {
  const unconfirmed = position.rubric_status === "unconfirmed";
  return (
    <p
      className={`rubric-line ${unconfirmed ? "rubric-line--unconfirmed" : "rubric-line--confirmed"}`}
      data-testid="rubric-status"
    >
      <Icon name={unconfirmed ? "alert-triangle" : "check"} />
      <span>
        Rubric <strong>{position.rubric_status}</strong>, version{" "}
        <strong className="num">{position.rubric_version}</strong>
        {unconfirmed &&
          " — scores for this position carry the label “rubric unconfirmed” until you confirm."}
      </span>
    </p>
  );
}

export function PositionEditor({ positionId }: { positionId: string }) {
  const position = useQuery({
    queryKey: ["position", positionId],
    queryFn: () => fetchPosition(positionId),
    // The requirements appear when the worker finishes the setup job.
    refetchInterval: (query) => {
      const status = query.state.data?.setup_status;
      return status === "pending" || status === "running" ? 3000 : false;
    },
  });

  return (
    <div className="requirements">
      {position.isPending && <Loading />}
      {position.isError && (
        <ErrorNotice message={position.error.message} onRetry={() => void position.refetch()} />
      )}
      {position.data && (
        <>
          <div className="requirements__head">
            <div className="page-head">
              <h1 className="h1">{position.data.filename ?? "Position"}</h1>
              <Link href={href({ name: "ranking", positionId })}>Ranked list</Link>
            </div>
            <RubricLine position={position.data} />
          </div>
          {position.data.setup_status === "failed" && (
            <ErrorNotice message={position.data.setup_message ?? ""} />
          )}
          {(position.data.setup_status === "pending" || position.data.setup_status === "running") && (
            <div>
              <Loading>Extracting the requirements from the posting…</Loading>
            </div>
          )}
          {position.data.setup_status === "done" && (
            // Re-created for a new version, so the draft starts from what the server now holds.
            <RequirementsForm
              key={`${position.data.id}:${position.data.rubric_version}`}
              position={position.data}
            />
          )}
        </>
      )}
    </div>
  );
}
