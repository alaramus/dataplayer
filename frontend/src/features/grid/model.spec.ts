import { describe, expect, it, vi } from "vitest"

import type { FetchResult } from "@/client"

import { cellPresentation, shouldOpenViewer, toGridRows } from "./model"

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

describe("typed cell presentation", () => {
  it.each([
    [null, "string", { text: "∅", align: "left", tone: "null" }],
    ["9007199254740993", "number", { text: "9007199254740993", align: "right", tone: "default" }],
    ["true", "boolean", { text: "true", align: "center", tone: "default" }],
  ] as const)("presents %s as %s", (value, category, expected) => {
    expect(cellPresentation(value, { sql: category, category })).toMatchObject(expected)
  })

  it("keeps date and time text unchanged without locale formatters", () => {
    const numberFormat = vi.spyOn(Intl, "NumberFormat")
    const dateTimeFormat = vi.spyOn(Intl, "DateTimeFormat")
    const value = "2026-08-27T14:30:00+00:00"

    expect(cellPresentation(value, { sql: "timestamptz", category: "datetime" }).text).toBe(
      value
    )
    expect(numberFormat).not.toHaveBeenCalled()
    expect(dateTimeFormat).not.toHaveBeenCalled()
  })

  it("uses monospace for UUID and binary text", () => {
    expect(
      cellPresentation("550e8400-e29b-41d4-a716-446655440000", {
        sql: "uuid",
        category: "uuid",
      }).monospace
    ).toBe(true)
    expect(cellPresentation("0xCAFE", { sql: "bytea", category: "binary" }).monospace).toBe(
      true
    )
  })

  it("opens complex and truncated values in the full viewer", () => {
    expect(shouldOpenViewer("{}", { sql: "jsonb", category: "json" })).toBe(true)
    expect(shouldOpenViewer("{1,2}", { sql: "integer[]", category: "array" })).toBe(true)
    expect(shouldOpenViewer("0xCAFE", { sql: "bytea", category: "binary" })).toBe(true)
    expect(shouldOpenViewer("x".repeat(121), { sql: "text", category: "string" })).toBe(true)
    expect(shouldOpenViewer("short", { sql: "text", category: "string" })).toBe(false)
  })
})
