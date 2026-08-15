import { describe, expect, it } from "vitest"

import { displayValue, toGridColumns, toGridRows } from "./rows"
import type { FetchResult } from "@/client"

const RESULT: FetchResult = {
  columns: [
    { name: "id", data_type: "uuid" },
    { name: "name", data_type: "text" },
  ],
  rows: [
    ["a1", "first"],
    ["b2", null],
  ],
  has_more: false,
}

describe("toGridColumns", () => {
  it("keeps the column order", () => {
    expect(toGridColumns(RESULT).map((column) => column.name)).toEqual(["id", "name"])
  })

  it("leaves grid sorting off, because the server sorts the whole relation", () => {
    expect(toGridColumns(RESULT).every((column) => column.sortable)).toBe(false)
  })
})

describe("toGridRows", () => {
  it("maps positional values onto column names", () => {
    const rows = toGridRows(RESULT)

    expect(rows[0]).toEqual({ id: "a1", name: "first" })
    expect(rows[1]).toEqual({ id: "b2", name: null })
  })

  it("returns one object per row", () => {
    expect(toGridRows(RESULT)).toHaveLength(2)
  })

  it("handles an empty page", () => {
    expect(toGridRows({ ...RESULT, rows: [] })).toEqual([])
  })
})

describe("displayValue", () => {
  it("marks null distinctly from an empty string", () => {
    expect(displayValue(null)).not.toBe("")
    expect(displayValue("")).toBe("")
  })

  it("serialises objects rather than showing [object Object]", () => {
    expect(displayValue({ a: 1 })).toBe('{"a":1}')
  })

  it("keeps numbers and booleans readable", () => {
    expect(displayValue(0)).toBe("0")
    expect(displayValue(false)).toBe("false")
  })
})
