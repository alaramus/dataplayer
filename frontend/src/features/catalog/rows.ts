import type { FetchResult } from "@/client"

export interface GridColumn {
  name: string
  label: string
  field: string
  align: "left"
  /**
   * Always false: sorting is done by the server over the whole relation.
   * Leaving it true makes QTh render its own indicator and sort the current
   * page on top of that, which is a different and misleading order.
   */
  sortable: false
}

/** QTable wants columns as descriptors and rows as objects keyed by column. */
export function toGridColumns(result: FetchResult): GridColumn[] {
  return result.columns.map((column) => ({
    name: column.name,
    label: column.name,
    field: column.name,
    align: "left" as const,
    sortable: false as const,
  }))
}

/**
 * Turn positional rows into objects for the grid.
 *
 * The API sends arrays so that a wide result does not repeat column names in
 * every row; the grid addresses cells by key, so the mapping happens here and
 * nowhere else.
 */
export function toGridRows(result: FetchResult): Record<string, unknown>[] {
  return result.rows.map((row) => {
    const record: Record<string, unknown> = {}
    result.columns.forEach((column, index) => {
      record[column.name] = row[index]
    })
    return record
  })
}

/** Render a cell value for display without hiding the difference from a string. */
export function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "∅"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}
