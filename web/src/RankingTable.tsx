import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { Fragment, useMemo } from "react";

import type { RankingRow } from "./api";
import { href } from "./route";
import {
  failedMandatoryLabel,
  formatScore,
  SECTION_LABEL,
  sectionStarts,
  statusLabel,
  toCheck,
  type Section,
} from "./ranking";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { Link } from "./ui/Link";
import { Tooltip } from "./ui/Tooltip";
import "./ui/Badge.css";
import "./ui/DocumentState.css";
import "./ui/Table.css";
import "./RankingTable.css";

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, RankingRow>();

const NUMERIC = new Set(["rank", "score", "to-check"]);

function CandidateCell({ row }: { row: RankingRow }) {
  return (
    <>
      {row.candidate_name === null ? (
        <span className="name-missing">(name not found)</span>
      ) : (
        <span className="candidate-name">{row.candidate_name}</span>
      )}
      <span className="row-sub">{row.filename}</span>
    </>
  );
}

function MandatoryCell({ row }: { row: RankingRow }) {
  const label = failedMandatoryLabel(row);
  if (row.status === "done" && row.mandatory_failed) {
    return (
      <span className="state state--not-met">
        <Icon name="x-circle" />
        {label}
      </span>
    );
  }
  return <span className="cell-muted">{label}</span>;
}

function StatusCell({ status }: { status: RankingRow["status"] }) {
  const failed = status === "failed";
  return (
    <span className={failed ? "state state--attention" : "state"}>
      <Icon name={failed ? "alert-circle" : "check"} />
      {statusLabel(status)}
    </span>
  );
}

function ToCheckCell({ row }: { row: RankingRow }) {
  const { total, tooltip } = toCheck(row);
  if (total === null) {
    return <span className="count">–</span>;
  }
  return (
    <Tooltip content={tooltip}>
      {(describedBy) => (
        // Focusable, so the breakdown is reachable by keyboard.
        <span className={total > 0 ? "badge badge--caution" : "count"} tabIndex={0} aria-describedby={describedBy}>
          {total > 0 && <Icon name="alert-triangle" />}
          <span className="num">{total}</span>
        </span>
      )}
    </Tooltip>
  );
}

// No sorting here: the API's order (assessed first, then no failed mandatory requirement, then
// score) is the ranking, and a client-side sort would contradict it (§2.4).
function buildColumns(positionId: string) {
  return helper.columns([
    helper.display({
      id: "rank",
      header: "#",
      cell: ({ row }) => <span className="cell-muted">{row.index + 1}</span>,
    }),
    helper.display({
      id: "candidate",
      header: "Candidate",
      cell: ({ row }) => <CandidateCell row={row.original} />,
    }),
    helper.display({
      id: "score",
      header: "Score",
      cell: ({ row }) => <span className="score">{formatScore(row.original)}</span>,
    }),
    helper.display({
      id: "mandatory",
      header: "Failed mandatory",
      cell: ({ row }) => <MandatoryCell row={row.original} />,
    }),
    helper.display({
      id: "status",
      header: "Assessment",
      cell: ({ row }) => <StatusCell status={row.original.status} />,
    }),
    helper.display({
      id: "to-check",
      header: "To check",
      cell: ({ row }) => <ToCheckCell row={row.original} />,
    }),
    helper.display({
      id: "open",
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <Link
          href={href({
            name: "assessment",
            positionId,
            assessmentId: row.original.assessment_id,
          })}
        >
          Check verdicts
        </Link>
      ),
    }),
  ]);
}

function SectionHeaderRow({ section, columns }: { section: Section; columns: number }) {
  return (
    <tr className="row--section">
      <th colSpan={columns} scope="colgroup">
        <span className="section-head">
          {SECTION_LABEL[section]}
          {section === "misses" && (
            <Tooltip
              placement="end"
              content="Ranked below all candidates who meet every mandatory requirement, whatever their score."
            >
              {(describedBy) => (
                <Button
                  variant="icon"
                  size="sm"
                  icon="help-circle"
                  aria-label="About this group"
                  aria-describedby={describedBy}
                />
              )}
            </Tooltip>
          )}
        </span>
      </th>
    </tr>
  );
}

export function RankingTable({ rows, positionId }: { rows: RankingRow[]; positionId: string }) {
  // Stable columns and row ids: the table renders each cell as a component, so new ones on every
  // poll would re-create the cells and drop the focus and the open tooltip.
  const columns = useMemo(() => buildColumns(positionId), [positionId]);
  const table = useTable({ features, columns, data: rows, getRowId: (row) => row.assessment_id });
  const starts = sectionStarts(rows);
  return (
    <div className="table-wrap">
      <table className="table ranking">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id} className={NUMERIC.has(header.column.id) ? "col-num" : undefined}>
                  {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const section = starts.get(row.index);
            const cells = row.getAllCells();
            return (
              <Fragment key={row.id}>
                {section !== undefined && <SectionHeaderRow section={section} columns={cells.length} />}
                <tr className={row.original.status === "failed" ? "row--failed" : undefined}>
                  {cells.map((cell) => (
                    <td key={cell.id} className={NUMERIC.has(cell.column.id) ? "col-num" : undefined}>
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
