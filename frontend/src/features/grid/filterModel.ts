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

// A condition has to fit on one line beside the others, and a cell may hold a
// paragraph. Both ceilings are about the chip and nothing else: what was sent
// is unaffected.
const MAX_SHOWN_VALUE = 40
const MAX_SHOWN_VALUES = 3

function quoted(value: string): string {
  const shown =
    value.length > MAX_SHOWN_VALUE ? `${value.slice(0, MAX_SHOWN_VALUE)}\u2026` : value
  return `"${shown}"`
}

/**
 * What an applied filter says, the value included.
 *
 * The value is the half that used to be missing. A page filtered to nothing
 * read as broken, because the condition on screen named the column and the
 * operator and left out the one thing that explained the empty result — and a
 * predicate that arrived by following a reference was never typed by anybody,
 * so there was nowhere else to see it (D106).
 */
export function describeFilter(filter: Filter): string {
  const head = `${filter.column} ${OPERATOR_LABELS[filter.op]}`
  // Written out rather than asked of NULL_OPERATORS: a set membership check
  // proves nothing to the compiler, and the branch below reads `value`.
  if (filter.op === "is_null" || filter.op === "is_not_null") return head
  if (filter.op === "in") {
    const shown = filter.values.slice(0, MAX_SHOWN_VALUES).map(quoted)
    const rest = filter.values.length - shown.length
    return `${head} ${shown.join(", ")}${rest > 0 ? ` +${rest} more` : ""}`
  }
  return `${head} ${quoted(filter.value)}`
}

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
