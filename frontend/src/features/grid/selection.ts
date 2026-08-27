import type { CellSelectionBounds } from "@tanstack/vue-table"

import type { GridRow } from "./types"

export interface VisibleGridColumn {
  id: string
  valueIndex: number
}

export function selectionMatrix(
  rows: readonly GridRow[],
  columns: readonly VisibleGridColumn[],
  bounds: readonly CellSelectionBounds[]
): (string | null)[][] {
  return bounds.flatMap((range) => {
    const selectedRows = rows.slice(range.minRowIndex, range.maxRowIndex + 1)
    const selectedColumns = columns.slice(range.minColumnIndex, range.maxColumnIndex + 1)
    return selectedRows.map((row) =>
      selectedColumns.map((column) => row.values[column.valueIndex] ?? null)
    )
  })
}
