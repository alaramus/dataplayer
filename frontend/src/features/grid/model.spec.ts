import { describe, expect, it } from "vitest"

import type { FetchResult } from "@/client"

import { toGridRows } from "./model"

const RESULT: FetchResult = {
  columns: [
    { name: "id", type: { sql: "bigint", category: "number" }, sortable: true },
    { name: "name", type: { sql: "text", category: "string" }, sortable: true },
  ],
  rows: [
    ["9007199254740993", "first"],
    [null, "second"],
  ],
  has_more: false,
}

describe("toGridRows", () => {
  it("gives page rows stable display ids without inventing a record key", () => {
    expect(toGridRows(RESULT, 100)).toEqual([
      { id: "100", values: ["9007199254740993", "first"] },
      { id: "101", values: [null, "second"] },
    ])
  })

  it("returns no rows for an empty page", () => {
    expect(toGridRows({ ...RESULT, rows: [] }, 0)).toEqual([])
  })
})
