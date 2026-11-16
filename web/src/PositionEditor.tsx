import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  fetchPosition,
  postAnswer,
  type AnswerRequest,
  type PositionDetail,
} from "./api";
import { newRow, removeRow, toDraft, toPayload, validate, type DraftRow } from "./draft";
import { RequirementsTable } from "./RequirementsTable";

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

  const problem = validate(rows);
  const dirty = JSON.stringify(rows) !== JSON.stringify(saved);
  const busy = answer.isPending;

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
    <section>
      <RequirementsTable
        rows={rows}
        disabled={busy}
        update={(key, patch) =>
          setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)))
        }
        remove={(key) => setRows((current) => removeRow(current, key))}
      />
      <p>
        <button type="button" disabled={busy} onClick={() => setRows((current) => [...current, newRow()])}>
          Add requirement
        </button>
      </p>
      {dirty && problem !== null && <p role="alert">{problem}</p>}
      {answer.isError && <p role="alert">{answer.error.message}</p>}
      {answer.isSuccess && !dirty && (
        <p>{answer.data.duplicate ? "Already saved." : "Saved."}</p>
      )}
      <p style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" disabled={busy || !dirty || problem !== null} onClick={save}>
          Save changes
        </button>
        <button
          type="button"
          disabled={busy || dirty || position.rubric_status === "confirmed" || rows.length === 0}
          onClick={confirm}
          title={dirty ? "Save your changes first, then confirm" : undefined}
        >
          Confirm requirements
        </button>
        {dirty && (
          <button type="button" disabled={busy} onClick={() => setRows(saved)}>
            Discard changes
          </button>
        )}
      </p>
    </section>
  );
}

export function PositionEditor({ positionId, onBack }: { positionId: string; onBack: () => void }) {
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
    <div>
      <p>
        <button type="button" onClick={onBack}>
          ← Positions
        </button>
      </p>
      {position.isPending && <p>Loading…</p>}
      {position.isError && <p role="alert">{position.error.message}</p>}
      {position.data && (
        <>
          <h2>{position.data.filename ?? "Position"}</h2>
          <p data-testid="rubric-status">
            Rubric <strong>{position.data.rubric_status}</strong>, version{" "}
            <strong>{position.data.rubric_version}</strong>
            {position.data.rubric_status === "unconfirmed" &&
              " — scores for this position carry the label “rubric unconfirmed” until you confirm."}
          </p>
          {position.data.setup_status === "failed" && (
            <p role="alert">{position.data.setup_message}</p>
          )}
          {(position.data.setup_status === "pending" || position.data.setup_status === "running") && (
            <p>Extracting the requirements from the posting…</p>
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
