import { describe, expect, it } from "vitest"

import type { CellSelectionBounds } from "@tanstack/vue-table"

import { selectedWholeRowIndexes, selectionMatrix } from "./selection"
import type { VisibleGridColumn } from "./selection"
import type { GridRow } from "./types"

const ROWS: GridRow[] = [
  { id: "10", values: ["1", "Ada", "hidden-a"] },
  { id: "11", values: ["2", "Grace", "hidden-b"] },
]
const VISIBLE: VisibleGridColumn[] = [
  { id: "id", valueIndex: 0 },
  { id: "name", valueIndex: 1 },
]

const bounds = (
  minRowIndex: number,
  maxRowIndex: number,
  minColumnIndex: number,
  maxColumnIndex: number
): CellSelectionBounds => ({ minRowIndex, maxRowIndex, minColumnIndex, maxColumnIndex })

describe("selection matrices", () => {
  it("resolves one cell", () => {
    expect(selectionMatrix(ROWS, VISIBLE, [bounds(0, 0, 1, 1)])).toEqual([["Ada"]])
  })

  it("resolves a dragged rectangle in row and display-column order", () => {
    expect(selectionMatrix(ROWS, VISIBLE, [bounds(0, 1, 0, 1)])).toEqual([
      ["1", "Ada"],
      ["2", "Grace"],
    ])
  })

  it("resolves a selected row through the same rectangle", () => {
    expect(selectionMatrix(ROWS, VISIBLE, [bounds(1, 1, 0, 1)])).toEqual([
      ["2", "Grace"],
    ])
  })

  it("resolves a selected visible column through the same rectangle", () => {
    expect(selectionMatrix(ROWS, VISIBLE, [bounds(0, 1, 1, 1)])).toEqual([
      ["Ada"],
      ["Grace"],
    ])
  })

  it("resolves the whole page without hidden columns", () => {
    expect(selectionMatrix(ROWS, VISIBLE, [bounds(0, 1, 0, 1)])).toEqual([
      ["1", "Ada"],
      ["2", "Grace"],
    ])
  })

  it("returns row indexes only for ranges spanning every visible column", () => {
    expect(selectedWholeRowIndexes([bounds(1, 1, 0, 1)], 2)).toEqual([1])
    expect(selectedWholeRowIndexes([bounds(0, 1, 1, 1)], 2)).toEqual([])
  })

  it("deduplicates overlapping whole-row ranges", () => {
    expect(
      selectedWholeRowIndexes([bounds(0, 1, 0, 1), bounds(1, 1, 0, 1)], 2)
    ).toEqual([0, 1])
  })
})
