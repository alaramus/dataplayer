/**
 * Where a pasted block lands, and whether it may.
 *
 * Pure so it can be tested without a grid: the caller supplies what is on
 * screen and what the source said about it, and gets back either the request
 * the server will be sent or the reason it will not be.
 */

import type { GridRow } from "./types"

export interface PasteColumn {
  name: string
  valueIndex: number
  editable: boolean
}

export interface PasteTarget {
  /** The top-left cell of the selection: where the block's first cell goes. */
  rowIndex: number
  columnIndex: number
}

export interface PasteRow {
  row_handle: string
  cells: { column: string; value: string | null }[]
}

export type PastePlan =
  | { ok: true; rows: PasteRow[] }
  | { ok: false; reason: string }

/** The whole request is bounded, as the server's own contract is. */
const MAX_ROWS = 500
const MAX_CELLS = 2000

export function planPaste(
  block: readonly (readonly (string | null)[])[],
  rows: readonly GridRow[],
  handles: readonly (string | null)[],
  columns: readonly PasteColumn[],
  at: PasteTarget
): PastePlan {
  const height = block.length
  const width = block[0]?.length ?? 0
  if (height === 0 || width === 0) return { ok: false, reason: "Nothing to paste" }

  // Nothing is truncated and no row is invented: a block that does not fit is
  // refused whole, so what lands is always what was pasted.
  if (at.rowIndex + height > rows.length) {
    return {
      ok: false,
      reason: `This block is ${height} rows tall and only ${
        rows.length - at.rowIndex
      } are loaded below the selection`,
    }
  }
  if (at.columnIndex + width > columns.length) {
    return {
      ok: false,
      reason: `This block is ${width} columns wide and only ${
        columns.length - at.columnIndex
      } are shown to the right of the selection`,
    }
  }

  const landing = columns.slice(at.columnIndex, at.columnIndex + width)
  const uneditable = landing.find((column) => !column.editable)
  if (uneditable !== undefined) {
    return { ok: false, reason: `Column ${uneditable.name} cannot be edited` }
  }

  const planned: PasteRow[] = []
  for (let line = 0; line < height; line += 1) {
    const rowAt = at.rowIndex + line
    const row = rows[rowAt]
    const handle = handles[rowAt]
    // The source issues a handle only where it can version a row (D25); a page
    // without them cannot be edited at all, and half of one cannot either.
    if (row === undefined || typeof handle !== "string") {
      return { ok: false, reason: "This relation cannot identify one of those rows" }
    }
    const cells = landing
      .map((column, index) => ({
        column: column.name,
        value: block[line]?.[index] ?? null,
      }))
      // A cell already holding what is being pasted into it is not a change,
      // and leaving it out keeps a wide paste inside the ceiling.
      .filter(
        (cell, index) =>
          row.values[landing[index]?.valueIndex ?? -1] !== cell.value
      )
    if (cells.length > 0) planned.push({ row_handle: handle, cells })
  }

  if (planned.length === 0) return { ok: false, reason: "Those cells already hold that" }
  if (planned.length > MAX_ROWS) {
    return { ok: false, reason: `A paste may cover at most ${MAX_ROWS} rows` }
  }
  const total = planned.reduce((sum, row) => sum + row.cells.length, 0)
  if (total > MAX_CELLS) {
    return { ok: false, reason: `A paste may carry at most ${MAX_CELLS} cells` }
  }
  return { ok: true, rows: planned }
}

export interface InsertablePasteColumn {
  name: string
  insertable: boolean
}

export interface RowFill {
  values: { column: string; value: string | null }[]
  /** Columns the line covered that the source fills itself. */
  skipped: string[]
}

export type RowPastePlan = { ok: true; fill: RowFill } | { ok: false; reason: string }

/**
 * A copied line read back into the fields of a row being inserted.
 *
 * Positional, and that is exact rather than lucky: the grid and the insert row
 * are built from the same ordered list of visible columns, so the nth value of
 * a copied line belongs to the nth field. What the source fills itself — an
 * identity, a generated column — is left out rather than refused, since a
 * copied row always carries those and refusing would make the gesture useless.
 */
export function planRowPaste(
  block: readonly (readonly (string | null)[])[],
  columns: readonly InsertablePasteColumn[]
): RowPastePlan {
  if (block.length !== 1) {
    return { ok: false, reason: "One row is inserted at a time" }
  }
  const line = block[0] ?? []
  if (line.length === 0) return { ok: false, reason: "Nothing to paste" }
  if (line.length > columns.length) {
    return {
      ok: false,
      reason: `That line has ${line.length} values and ${columns.length} columns are shown`,
    }
  }
  const values: { column: string; value: string | null }[] = []
  const skipped: string[] = []
  line.forEach((value, index) => {
    const column = columns[index]
    if (column === undefined) return
    if (column.insertable) values.push({ column: column.name, value })
    else skipped.push(column.name)
  })
  if (values.length === 0) {
    return { ok: false, reason: "The source fills every one of those columns itself" }
  }
  return { ok: true, fill: { values, skipped } }
}
