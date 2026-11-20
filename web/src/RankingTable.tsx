import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";

import type { RankingRow } from "./api";
import { failedMandatoryLabel, formatScore, statusLabel } from "./ranking";

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, RankingRow>();

const UNCONFIRMED_LABEL = "rubric unconfirmed";

// No sorting here: the API's order (assessed first, then no failed mandatory requirement, then
// score) is the ranking, and a client-side sort would contradict it (§2.4).
function buildColumns(onOpen: (assessmentId: string) => void) {
  return helper.columns([
    helper.display({ id: "rank", header: "#", cell: ({ row }) => row.index + 1 }),
    helper.display({
      id: "candidate",
      header: "Candidate",
      cell: ({ row }) => (
        <>
          <strong>{row.original.candidate_name ?? "(name not found)"}</strong>
          <br />
          <small style={{ color: "#555" }}>{row.original.filename}</small>
        </>
      ),
    }),
    helper.display({ id: "score", header: "Score", cell: ({ row }) => formatScore(row.original) }),
    helper.display({
      id: "mandatory",
      header: "Failed mandatory",
      cell: ({ row }) => failedMandatoryLabel(row.original),
    }),
    helper.display({
      id: "status",
      header: "Assessment",
      cell: ({ row }) => (
        <>
          {statusLabel(row.original.status)}
          {row.original.rubric_unconfirmed && (
            <span style={{ marginLeft: "0.5rem", padding: "0 0.4rem", border: "1px solid #b26a00" }}>
              {UNCONFIRMED_LABEL}
            </span>
          )}
        </>
      ),
    }),
    helper.display({
      id: "flagged",
      header: "Unverified quotes",
      cell: ({ row }) => row.original.flagged_verdicts,
    }),
    helper.display({
      id: "open",
      header: "",
      cell: ({ row }) => (
        <button type="button" onClick={() => onOpen(row.original.assessment_id)}>
          Check verdicts
        </button>
      ),
    }),
  ]);
}

export function RankingTable({
  rows,
  onOpen,
}: {
  rows: RankingRow[];
  onOpen: (assessmentId: string) => void;
}) {
  const table = useTable({ features, columns: buildColumns(onOpen), data: rows });
  return (
    <table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead>
        {table.getHeaderGroups().map((group) => (
          <tr key={group.id}>
            {group.headers.map((header) => (
              <th key={header.id} style={{ textAlign: "left", padding: "0.25rem" }}>
                {header.isPlaceholder ? null : <table.FlexRender header={header} />}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.original.assessment_id} style={{ borderTop: "1px solid #ddd" }}>
            {row.getAllCells().map((cell) => (
              <td key={cell.id} style={{ padding: "0.25rem", verticalAlign: "top" }}>
                <table.FlexRender cell={cell} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
