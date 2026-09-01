import type { TabularColumn } from "./tabular"
import type { Filter } from "./types"

export type FilterOp = Filter["op"]

export interface FilterDraft {
  column: string
  op: FilterOp
  value: string
  values: string[]
}

export const OPERATOR_LABELS: Record<FilterOp, string> = {
  eq: "equals",
  ne: "does not equal",
  gt: "greater than",
  gte: "greater than or equal",
  lt: "less than",
  lte: "less than or equal",
  contains: "contains",
  starts_with: "starts with",
  in: "is one of",
  is_null: "is null",
  is_not_null: "is not null",
}

const NULL_OPERATORS = new Set<FilterOp>(["is_null", "is_not_null"])

interface FilterColumn {
  id?: string
  name?: string
  type: TabularColumn["type"]
  filter_operators?: TabularColumn["filter_operators"]
}

function columnId(column: FilterColumn): string {
  const id = column.id ?? column.name
  if (id === undefined) throw new Error("A filter column needs an id")
  return id
}

export function operatorOptions(column: FilterColumn): FilterOp[] {
  return [...(column.filter_operators ?? [])]
}

export function draftFor(column: FilterColumn, op?: FilterOp): FilterDraft {
  const selected = op ?? operatorOptions(column)[0]
  const id = columnId(column)
  if (selected === undefined) throw new Error(`Column "${id}" has no filter operator`)
  return { column: id, op: selected, value: "", values: [] }
}

export function validateDraft(draft: FilterDraft): string | null {
  if (draft.op === "in") return draft.values.length === 0 ? "Add at least one value" : null
  if (NULL_OPERATORS.has(draft.op)) return null
  return draft.value.length === 0 ? "Enter a value" : null
}

export function toFilter(draft: FilterDraft): Filter {
  if (draft.op === "in") {
    return { column: draft.column, op: "in", values: [...draft.values] }
  }
  if (draft.op === "is_null" || draft.op === "is_not_null") {
    return { column: draft.column, op: draft.op }
  }
  return { column: draft.column, op: draft.op, value: draft.value }
}
