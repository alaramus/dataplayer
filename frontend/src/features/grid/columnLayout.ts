import type { FetchColumn } from "@/client"

import type { StoredGridState } from "./types"

export type ColumnLayoutState = Pick<
  StoredGridState,
  "columnOrder" | "columnVisibility" | "columnSizing" | "pinnedLeft"
>

export interface WidthLimits {
  min: number
  max: number
}

export function autoFitWidth(
  header: string,
  values: readonly (string | null)[],
  measure: (text: string) => number,
  limits: WidthLimits
): number {
  const measured = Math.max(measure(header), ...values.map((value) => measure(value ?? "null")))
  return Math.min(limits.max, Math.max(limits.min, measured))
}

export function defaultColumnLayout(columns: readonly FetchColumn[]): ColumnLayoutState {
  return {
    columnOrder: columns.map((column) => column.name),
    columnVisibility: {},
    columnSizing: {},
    pinnedLeft: [],
  }
}

export function moveColumn(
  layout: ColumnLayoutState,
  columnName: string,
  delta: -1 | 1
): ColumnLayoutState {
  const index = layout.columnOrder.indexOf(columnName)
  const target = index + delta
  if (index < 0 || target < 0 || target >= layout.columnOrder.length) {
    return { ...layout, columnOrder: [...layout.columnOrder] }
  }

  const columnOrder = [...layout.columnOrder]
  const other = columnOrder[target]
  if (other === undefined) return { ...layout, columnOrder }
  columnOrder[target] = columnName
  columnOrder[index] = other
  return { ...layout, columnOrder }
}
