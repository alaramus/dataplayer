import { describe, expect, it } from "vitest"

import { planPaste, planRowPaste } from "./paste"
import type { PasteColumn } from "./paste"
import type { GridRow } from "./types"

const COLUMNS: PasteColumn[] = [
  { name: "id", valueIndex: 0, editable: false },
  { name: "name", valueIndex: 1, editable: true },
  { name: "note", valueIndex: 2, editable: true },
]

const ROWS: GridRow[] = [
  { id: "0", values: ["1", "ann", "x"] },
  { id: "1", values: ["2", "bob", "y"] },
]

const HANDLES = ["h0", "h1"]

describe("where a pasted block lands", () => {
  it("maps the block onto the cells right and down from the selection", () => {
    const plan = planPaste(
      [
        ["anna", "p"],
        ["bobby", "q"],
      ],
      ROWS,
      HANDLES,
      COLUMNS,
      { rowIndex: 0, columnIndex: 1 }
    )

    expect(plan).toEqual({
      ok: true,
      rows: [
        {
          row_handle: "h0",
          cells: [
            { column: "name", value: "anna" },
            { column: "note", value: "p" },
          ],
        },
        {
          row_handle: "h1",
          cells: [
            { column: "name", value: "bobby" },
            { column: "note", value: "q" },
          ],
        },
      ],
    })
  })

  it("leaves out a cell that already holds what is being pasted into it", () => {
    const plan = planPaste([["ann", "p"]], ROWS, HANDLES, COLUMNS, {
      rowIndex: 0,
      columnIndex: 1,
    })

    expect(plan).toEqual({
      ok: true,
      rows: [{ row_handle: "h0", cells: [{ column: "note", value: "p" }] }],
    })
  })

  it("refuses a block taller than what is loaded rather than inventing a row", () => {
    const plan = planPaste([["a"], ["b"], ["c"]], ROWS, HANDLES, COLUMNS, {
      rowIndex: 0,
      columnIndex: 1,
    })

    expect(plan.ok).toBe(false)
    expect(plan.ok === false && plan.reason).toContain("3 rows tall")
  })

  it("refuses a block wider than the columns to the right of the selection", () => {
    const plan = planPaste([["a", "b", "c"]], ROWS, HANDLES, COLUMNS, {
      rowIndex: 0,
      columnIndex: 1,
    })

    expect(plan.ok).toBe(false)
    expect(plan.ok === false && plan.reason).toContain("3 columns wide")
  })

  it("refuses a landing that covers a column the source will not edit", () => {
    const plan = planPaste([["a", "b"]], ROWS, HANDLES, COLUMNS, {
      rowIndex: 0,
      columnIndex: 0,
    })

    expect(plan.ok).toBe(false)
    expect(plan.ok === false && plan.reason).toContain("id cannot be edited")
  })

  it("refuses a page whose rows the source cannot identify", () => {
    const plan = planPaste([["a"]], ROWS, [null, null], COLUMNS, {
      rowIndex: 0,
      columnIndex: 1,
    })

    expect(plan.ok).toBe(false)
    expect(plan.ok === false && plan.reason).toContain("cannot identify")
  })
})

describe("a copied line read into a row being inserted", () => {
  const INSERT_COLUMNS = [
    { name: "id", insertable: false },
    { name: "name", insertable: true },
    { name: "note", insertable: true },
  ]

  it("pairs values with fields by position and leaves the source its own", () => {
    const plan = planRowPaste([["7", "ann", null]], INSERT_COLUMNS)

    expect(plan).toEqual({
      ok: true,
      fill: {
        values: [
          { column: "name", value: "ann" },
          { column: "note", value: null },
        ],
        skipped: ["id"],
      },
    })
  })

  it("takes a line shorter than the columns shown", () => {
    const plan = planRowPaste([["7", "ann"]], INSERT_COLUMNS)

    expect(plan.ok).toBe(true)
    expect(plan.ok === true && plan.fill.values).toEqual([
      { column: "name", value: "ann" },
    ])
  })

  it("refuses more than one line, since one row is inserted at a time", () => {
    const plan = planRowPaste([["7", "ann"], ["8", "bob"]], INSERT_COLUMNS)

    expect(plan.ok).toBe(false)
    expect(plan.ok === false && plan.reason).toContain("One row")
  })

  it("refuses a line wider than the columns shown", () => {
    const plan = planRowPaste([["7", "ann", "x", "extra"]], INSERT_COLUMNS)

    expect(plan.ok).toBe(false)
    expect(plan.ok === false && plan.reason).toContain("4 values")
  })
})
