import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { createContext, useContext } from "react";

import type { Kind } from "./api";
import { MAX_WEIGHT, MIN_WEIGHT, type DraftField, type DraftProblem, type DraftRow } from "./draft";
import { Button } from "./ui/Button";
import { NumberInput, Select, TextInput } from "./ui/Inputs";
import "./ui/Table.css";
import "./RequirementsTable.css";

interface Actions {
  rows: DraftRow[];
  update: (key: string, patch: Partial<DraftRow>) => void;
  remove: (key: string) => void;
  disabled: boolean;
  // The problem on screen, if any: the field it names is marked.
  problem: DraftProblem | null;
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

// `n` is the number HR sees: the row's position, from 1. It names each control, so the names do
// not repeat from row to row.
type CellProps = { row: DraftRow; n: number };

function isNamed(problem: DraftProblem | null, n: number, field: DraftField): boolean {
  return problem !== null && problem.index === n - 1 && problem.field === field;
}

function TextCell({ row, n }: CellProps) {
  const { update, disabled, problem } = useActions();
  return (
    <TextInput
      aria-label={`Requirement ${n}`}
      value={row.text}
      disabled={disabled}
      invalid={isNamed(problem, n, "text")}
      onChange={(event) => update(row.key, { text: event.target.value })}
    />
  );
}

function KindCell({ row, n }: CellProps) {
  const { update, disabled } = useActions();
  return (
    <Select
      aria-label={`Type, requirement ${n}`}
      value={row.kind}
      disabled={disabled}
      invalid={false}
      onChange={(event) => update(row.key, { kind: event.target.value as Kind })}
    >
      <option value="mandatory">Mandatory</option>
      <option value="nice_to_have">Nice to have</option>
    </Select>
  );
}

function WeightCell({ row, n }: CellProps) {
  const { update, disabled, problem } = useActions();
  return (
    <NumberInput
      aria-label={`Weight, requirement ${n}`}
      min={MIN_WEIGHT}
      max={MAX_WEIGHT}
      step={1}
      value={row.weight}
      disabled={disabled}
      invalid={isNamed(problem, n, "weight")}
      onChange={(event) => update(row.key, { weight: event.target.value })}
    />
  );
}

function MonthsCell({ row, n }: CellProps) {
  const { update, disabled, problem } = useActions();
  return (
    <NumberInput
      aria-label={`Minimum months, requirement ${n}`}
      min={1}
      step={1}
      value={row.minMonths}
      disabled={disabled}
      invalid={isNamed(problem, n, "minMonths")}
      onChange={(event) => update(row.key, { minMonths: event.target.value })}
    />
  );
}

function ParentCell({ row, n }: CellProps) {
  const { rows, update, disabled, problem } = useActions();
  return (
    <Select
      aria-label={`Parent, requirement ${n}`}
      value={row.parentKey ?? ""}
      disabled={disabled}
      invalid={isNamed(problem, n, "parentKey")}
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
    </Select>
  );
}

function RemoveCell({ row, n }: CellProps) {
  const { remove, disabled } = useActions();
  const name = `Remove requirement ${n}`;
  return (
    <Button
      variant="icon"
      size="sm"
      icon="trash"
      danger
      aria-label={name}
      title={name}
      disabled={disabled}
      onClick={() => remove(row.key)}
    />
  );
}

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, DraftRow>();

// Rows are never sorted, so `row.index` is the position in the draft.
const columns = helper.columns([
  helper.display({ id: "number", header: "#", cell: ({ row }) => row.index + 1 }),
  helper.display({
    id: "text",
    header: "Requirement",
    cell: ({ row }) => <TextCell row={row.original} n={row.index + 1} />,
  }),
  helper.display({
    id: "kind",
    header: "Type",
    cell: ({ row }) => <KindCell row={row.original} n={row.index + 1} />,
  }),
  helper.display({
    id: "weight",
    header: "Weight (1–5)",
    cell: ({ row }) => <WeightCell row={row.original} n={row.index + 1} />,
  }),
  helper.display({
    id: "months",
    header: "Minimum months",
    cell: ({ row }) => <MonthsCell row={row.original} n={row.index + 1} />,
  }),
  helper.display({
    id: "parent",
    header: "Parent",
    cell: ({ row }) => <ParentCell row={row.original} n={row.index + 1} />,
  }),
  helper.display({
    id: "remove",
    header: "Remove",
    cell: ({ row }) => <RemoveCell row={row.original} n={row.index + 1} />,
  }),
]);

export function RequirementsTable({ add, ...actions }: Actions & { add: () => void }) {
  const table = useTable({ features, columns, data: actions.rows });

  return (
    <ActionsContext.Provider value={actions}>
      <div className="editor">
        <div className="editor__scroll">
          <table className="table editor__table" aria-label="Requirements">
            <colgroup>
              {table.getAllLeafColumns().map((column) => (
                <col key={column.id} className={`editor__col-${column.id}`} />
              ))}
            </colgroup>
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id} className={`editor__cell-${header.column.id}`}>
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
                    <td key={cell.id} className={`editor__cell-${cell.column.id}`}>
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="editor__foot">
          <Button variant="ghost" size="sm" icon="plus" disabled={actions.disabled} onClick={add}>
            Add requirement
          </Button>
        </div>
      </div>
    </ActionsContext.Provider>
  );
}
