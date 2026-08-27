import type { CellSelectionBounds } from "@tanstack/vue-table"

import type { GridRow } from "./types"

export interface VisibleGridColumn {
  id: string
  valueIndex: number
}

export function selectedWholeRowIndexes(
  bounds: readonly CellSelectionBounds[],
  visibleColumnCount: number
): number[] {
  if (visibleColumnCount === 0) return []
  const indexes = new Set<number>()
  for (const range of bounds) {
    if (range.minColumnIndex !== 0 || range.maxColumnIndex !== visibleColumnCount - 1) continue
    for (let index = range.minRowIndex; index <= range.maxRowIndex; index += 1) {
      indexes.add(index)
    }
  }
  return [...indexes].sort((left, right) => left - right)
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
