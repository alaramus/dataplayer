import type { CellSelectionBounds } from "@tanstack/vue-table"
import type { CSSProperties } from "vue"

import type { FetchColumn } from "@/client"

import type { VisibleGridColumn } from "./selection"
import type { GridRow } from "./types"

/**
 * One column understood by the shared tabular presentation.
 *
 * `id` is identity and may be positional; `label` is only what the user sees.
 * Relations currently use their source column name for both. Query results can
 * therefore admit duplicate or empty labels without giving TanStack duplicate
 * column ids.
 */
export interface TabularColumn {
  id: string
  label: string
  type: FetchColumn["type"]
  sortable: boolean
  filter_operators: FetchColumn["filter_operators"]
  editable?: boolean
}

export interface TabularPasteRequest {
  bounds: CellSelectionBounds
  columns: VisibleGridColumn[]
}

export interface TabularVisibleColumn extends VisibleGridColumn {
  column: TabularColumn
  pinned: boolean
  style: CSSProperties
}

export interface TabularEditRequest {
  row: GridRow
  rowIndex: number
  column: TabularColumn
  value: string | null
}

export function tabularColumns(columns: readonly FetchColumn[]): TabularColumn[] {
  return columns.map((column) => ({
    id: column.name,
    label: column.name,
    type: column.type,
    sortable: column.sortable === true,
    filter_operators: column.filter_operators ?? [],
    editable: column.editable,
  }))
}

export function columnOf(
  columns: readonly TabularColumn[],
  id: string
): TabularColumn | undefined {
  return columns.find((column) => column.id === id)
}
