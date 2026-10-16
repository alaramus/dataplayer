import { t } from "@/shared/i18n"

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
  get eq() {
    return t("grid.filter.op.eq")
  },
  get ne() {
    return t("grid.filter.op.ne")
  },
  get gt() {
    return t("grid.filter.op.gt")
  },
  get gte() {
    return t("grid.filter.op.gte")
  },
  get lt() {
    return t("grid.filter.op.lt")
  },
  get lte() {
    return t("grid.filter.op.lte")
  },
  get contains() {
    return t("grid.filter.op.contains")
  },
  get starts_with() {
    return t("grid.filter.op.starts_with")
  },
  get in() {
    return t("grid.filter.op.in")
  },
  get is_null() {
    return t("grid.filter.op.is_null")
  },
  get is_not_null() {
    return t("grid.filter.op.is_not_null")
  },
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
  // Narrowed by the property and not by `op`: the generated union is a set of
  // intersections, and a comparison against `op` does not narrow across them.
  if ("values" in filter) {
    const shown = filter.values.slice(0, MAX_SHOWN_VALUES).map(quoted)
    const rest = filter.values.length - shown.length
    return `${head} ${shown.join(", ")}${rest > 0 ? ` ${t("grid.filter.more", { n: rest })}` : ""}`
  }
  return "value" in filter ? `${head} ${quoted(filter.value)}` : head
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
  if (draft.op === "in") return draft.values.length === 0 ? t("grid.filter.add_value") : null
  if (NULL_OPERATORS.has(draft.op)) return null
  return draft.value.length === 0 ? t("grid.filter.enter_value") : null
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
