import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { createContext, useContext } from "react";

import type { Kind } from "./api";
import { MAX_WEIGHT, MIN_WEIGHT, type DraftRow } from "./draft";

interface Actions {
  rows: DraftRow[];
  update: (key: string, patch: Partial<DraftRow>) => void;
  remove: (key: string) => void;
  disabled: boolean;
}

// Columns live at module scope (the table needs stable inputs), so the cells reach the draft
// through context instead of closing over it.
const ActionsContext = createContext<Actions | null>(null);

function useActions(): Actions {
  const actions = useContext(ActionsContext);
  if (actions === null) {
    throw new Error("requirement cells must render inside RequirementsTable");
  }
  return actions;
}

function TextCell({ row }: { row: DraftRow }) {
  const { update, disabled } = useActions();
  return (
    <input
      aria-label="Requirement text"
      style={{ width: "100%", minWidth: "16rem" }}
      value={row.text}
      disabled={disabled}
      onChange={(event) => update(row.key, { text: event.target.value })}
    />
  );
}

function KindCell({ row }: { row: DraftRow }) {
  const { update, disabled } = useActions();
  return (
    <select
      aria-label="Type"
      value={row.kind}
      disabled={disabled}
      onChange={(event) => update(row.key, { kind: event.target.value as Kind })}
    >
      <option value="mandatory">Mandatory</option>
      <option value="nice_to_have">Nice to have</option>
    </select>
  );
}

function NumberCell({ row, field }: { row: DraftRow; field: "weight" | "minMonths" }) {
  const { update, disabled } = useActions();
  return (
    <input
      aria-label={field === "weight" ? "Weight" : "Minimum months"}
      type="number"
      min={field === "weight" ? MIN_WEIGHT : 1}
      max={field === "weight" ? MAX_WEIGHT : undefined}
      style={{ width: "5rem" }}
      value={row[field]}
      disabled={disabled}
      onChange={(event) => update(row.key, { [field]: event.target.value })}
    />
  );
}

function ParentCell({ row }: { row: DraftRow }) {
  const { rows, update, disabled } = useActions();
  return (
    <select
      aria-label="Parent requirement"
      value={row.parentKey ?? ""}
      disabled={disabled}
      onChange={(event) => update(row.key, { parentKey: event.target.value || null })}
    >
      <option value="">None</option>
      {rows.map((other, index) =>
        other.key === row.key ? null : (
          <option key={other.key} value={other.key}>
            {`${index + 1}. ${other.text.slice(0, 40) || "(empty)"}`}
          </option>
        ),
      )}
    </select>
  );
}

function RemoveCell({ row }: { row: DraftRow }) {
  const { remove, disabled } = useActions();
  return (
    <button type="button" disabled={disabled} onClick={() => remove(row.key)}>
      Remove
    </button>
  );
}

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, DraftRow>();

const columns = helper.columns([
  helper.display({
    id: "number",
    header: "#",
    cell: ({ row }) => <NumberLabel rowKey={row.original.key} />,
  }),
  helper.display({ id: "text", header: "Requirement", cell: ({ row }) => <TextCell row={row.original} /> }),
  helper.display({ id: "kind", header: "Type", cell: ({ row }) => <KindCell row={row.original} /> }),
  helper.display({
    id: "weight",
    header: "Weight (1–5)",
    cell: ({ row }) => <NumberCell row={row.original} field="weight" />,
  }),
  helper.display({
    id: "minMonths",
    header: "Minimum months",
    cell: ({ row }) => <NumberCell row={row.original} field="minMonths" />,
  }),
  helper.display({ id: "parent", header: "Parent", cell: ({ row }) => <ParentCell row={row.original} /> }),
  helper.display({ id: "remove", header: "", cell: ({ row }) => <RemoveCell row={row.original} /> }),
]);

function NumberLabel({ rowKey }: { rowKey: string }) {
  const { rows } = useActions();
  return <>{rows.findIndex((row) => row.key === rowKey) + 1}</>;
}

export function RequirementsTable({ rows, update, remove, disabled }: Actions) {
  const table = useTable({ features, columns, data: rows });

  return (
    <ActionsContext.Provider value={{ rows, update, remove, disabled }}>
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
            <tr key={row.original.key}>
              {row.getAllCells().map((cell) => (
                <td key={cell.id} style={{ padding: "0.25rem" }}>
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </ActionsContext.Provider>
  );
}
