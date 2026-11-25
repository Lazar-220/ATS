import { useQuery } from "@tanstack/react-query";
import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { useId } from "react";

import { fetchPositions, type Position } from "./api";
import { href } from "./route";
import { EmptyState } from "./ui/EmptyState";
import { Icon } from "./ui/Icon";
import { Link } from "./ui/Link";
import { Loading } from "./ui/Loading";
import { ErrorNotice } from "./ui/Notice";
import "./ui/DocumentState.css";
import "./ui/Table.css";
import "./PositionsList.css";

const SETUP_LABEL = {
  pending: "waiting for the posting text",
  running: "extracting requirements…",
  done: "",
  failed: "failed",
} as const;

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, Position>();

const NUMERIC = new Set(["version", "requirements"]);

const columns = helper.columns([
  helper.display({
    id: "posting",
    header: "Posting",
    cell: ({ row }) => <span className="posting-name">{row.original.filename ?? row.original.id}</span>,
  }),
  helper.display({
    id: "rubric",
    header: "Rubric",
    cell: ({ row }) => {
      const status = row.original.rubric_status;
      if (status === "unconfirmed") {
        return (
          <span className="state state--caution">
            <Icon name="alert-triangle" />
            {status}
          </span>
        );
      }
      return (
        <span className={status === "confirmed" ? "state state--ok" : "state"}>
          {status === "confirmed" && <Icon name="check" />}
          {status}
        </span>
      );
    },
  }),
  helper.display({
    id: "version",
    header: "Version",
    cell: ({ row }) => row.original.rubric_version,
  }),
  helper.display({
    id: "requirements",
    header: "Requirements",
    cell: ({ row }) =>
      row.original.setup_status === "done" ? row.original.requirement_count : SETUP_LABEL[row.original.setup_status],
  }),
  helper.display({
    id: "actions",
    header: () => <span className="sr-only">Actions</span>,
    cell: ({ row }) => (
      <div className="row-actions">
        <Link href={href({ name: "requirements", positionId: row.original.id })}>Requirements</Link>
        <Link href={href({ name: "ranking", positionId: row.original.id })}>Ranked list</Link>
      </div>
    ),
  }),
]);

function PositionsTable({ positions }: { positions: Position[] }) {
  const table = useTable({ features, columns, data: positions });
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id} className={NUMERIC.has(header.column.id) ? "col-num" : undefined}>{header.isPlaceholder ? null : <table.FlexRender header={header} />}</th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.original.id}>
              {row.getAllCells().map((cell) => (
                <td key={cell.id} className={NUMERIC.has(cell.column.id) ? "col-num" : undefined}>
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

export function PositionsList() {
  const headingId = useId();
  const positions = useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 5000,
  });

  let body;
  if (positions.isPending) {
    body = <Loading />;
  } else if (positions.isError) {
    body = <ErrorNotice message={positions.error.message} onRetry={() => void positions.refetch()} />;
  } else if (positions.data.length === 0) {
    body = <EmptyState>No positions yet. Upload a posting and CVs above to create one.</EmptyState>;
  } else {
    body = <PositionsTable positions={positions.data} />;
  }
  return (
    <section className="section" aria-labelledby={headingId}>
      <h2 className="h2" id={headingId}>
        Positions
      </h2>
      <div>{body}</div>
    </section>
  );
}
