import type { Kind, RequirementPayload, RequirementRow } from "./api";

// What HR edits. Numbers stay strings so a half-typed value does not fight the input.
export interface DraftRow {
  // Existing rows keep their database id; new ones get a random one. Only used as a React key
  // and as the target of `parentKey`.
  key: string;
  text: string;
  kind: Kind;
  weight: string;
  minMonths: string;
  parentKey: string | null;
}

export const MIN_WEIGHT = 1;
export const MAX_WEIGHT = 5;

export function toDraft(requirements: RequirementRow[]): DraftRow[] {
  return requirements.map((req) => ({
    key: req.id,
    text: req.text,
    kind: req.kind,
    weight: String(req.weight),
    minMonths: req.min_months === null ? "" : String(req.min_months),
    parentKey: req.parent_id,
  }));
}

export function newRow(): DraftRow {
  return {
    key: crypto.randomUUID(),
    text: "",
    kind: "mandatory",
    weight: "1",
    minMonths: "",
    parentKey: null,
  };
}

// Removing a row detaches its children rather than deleting them: they are still requirements.
export function removeRow(rows: DraftRow[], key: string): DraftRow[] {
  return rows
    .filter((row) => row.key !== key)
    .map((row) => (row.parentKey === key ? { ...row, parentKey: null } : row));
}

function parseInteger(value: string): number | null {
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) ? Number(trimmed) : null;
}

function hasCycle(rows: DraftRow[]): boolean {
  const parentOf = new Map(rows.map((row) => [row.key, row.parentKey]));
  return rows.some((row) => {
    let current = row.parentKey;
    for (let steps = 0; current !== null && steps <= rows.length; steps += 1) {
      if (current === row.key) {
        return true;
      }
      current = parentOf.get(current) ?? null;
    }
    return false;
  });
}

// The first problem HR has to fix, or null. The server checks the same rules again.
export function validate(rows: DraftRow[]): string | null {
  if (rows.length === 0) {
    return "Add at least one requirement.";
  }
  for (const [index, row] of rows.entries()) {
    const label = `Requirement ${index + 1}`;
    if (row.text.trim() === "") {
      return `${label} has no text.`;
    }
    const weight = parseInteger(row.weight);
    if (weight === null || weight < MIN_WEIGHT || weight > MAX_WEIGHT) {
      return `${label}: weight must be a whole number from ${MIN_WEIGHT} to ${MAX_WEIGHT}.`;
    }
    if (row.minMonths.trim() !== "") {
      const months = parseInteger(row.minMonths);
      if (months === null || months < 1) {
        return `${label}: minimum months must be a whole number of at least 1, or empty.`;
      }
    }
  }
  return hasCycle(rows) ? "The parent links form a loop." : null;
}

// Call only after `validate` returned null. Labels are positions in the list, starting at 1.
export function toPayload(rows: DraftRow[]): RequirementPayload[] {
  const labels = new Map(rows.map((row, index) => [row.key, index + 1]));
  return rows.map((row, index) => ({
    id: index + 1,
    text: row.text.trim(),
    kind: row.kind,
    weight: parseInteger(row.weight) ?? MIN_WEIGHT,
    min_months: row.minMonths.trim() === "" ? null : parseInteger(row.minMonths),
    parent: row.parentKey === null ? null : (labels.get(row.parentKey) ?? null),
  }));
}
