import { describe, expect, it } from "vitest"

import { autoFitWidth, defaultColumnLayout, moveColumn } from "./columnLayout"

const COLUMNS = [{ id: "id" }, { id: "name" }]

describe("column layout", () => {
  it("auto fit measures the longest full value and clamps the result", () => {
    const measure = (text: string) => text.length * 8 + 20

    expect(autoFitWidth("name", ["A", "A much longer value"], measure, { min: 72, max: 480 })).toBe(
      172
    )
  })

  it("auto fit includes the header and respects both bounds", () => {
    const measure = (text: string) => text.length * 10

    expect(autoFitWidth("long_header", ["x"], measure, { min: 72, max: 100 })).toBe(100)
    expect(autoFitWidth("id", ["x"], measure, { min: 72, max: 480 })).toBe(72)
  })

  it("starts with server order, visible columns and no pinning", () => {
    expect(defaultColumnLayout(COLUMNS)).toEqual({
      columnOrder: ["id", "name"],
      columnVisibility: {},
      columnSizing: {},
      pinnedLeft: [],
    })
  })

  it("moves one column without mutating the original order", () => {
    const layout = defaultColumnLayout(COLUMNS)

    expect(moveColumn(layout, "name", -1).columnOrder).toEqual(["name", "id"])
    expect(layout.columnOrder).toEqual(["id", "name"])
  })
})
