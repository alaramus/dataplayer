import { describe, expect, it } from "vitest"

import type { TablesPreview } from "@/client"

import { choiceOf, copyScript, leftBehind, originNote, runChoice, startingPlace } from "./tablesCopy"

const PREVIEW: TablesPreview = {
  tables: [
    { node_id: "sales.orders", label: "sales.orders", name: "orders_copy", origin: "ticked", left_behind: ["2 triggers"] },
    { node_id: "sales.customers", label: "sales.customers", name: "customers", origin: "linked", left_behind: [] },
  ],
  links: "copy",
  keep_allowed: false,
  outside: [{ table: "sales.orders", target: "sales.customers" }],
  pointing: [],
  rows: true,
  place: "archive",
  statements: [
    { title: "Primary key orders_copy_pkey", sql: "ALTER TABLE a ADD PRIMARY KEY (id)", stage: "after" },
    { title: "Create table archive.orders_copy", sql: "CREATE TABLE a (id integer)", stage: "before" },
  ],
  loads: [{ node_id: "sales.orders", schema_name: "archive", name: "orders_copy", columns: ["id"] }],
  problems: [],
  warnings: [],
}

describe("a copy of tables", () => {
  it("asks for what the window holds, links left to the server until chosen", () => {
    expect(choiceOf({ names: { "sales.orders": "old_orders" }, rows: "structure", links: null, also: [] }))
      .toEqual({ names: { "sales.orders": "old_orders" }, rows: false, links: null, also: [] })
  })

  it("runs with every table named as shown and the links the plan used", () => {
    const choice = runChoice(
      { names: { "sales.orders": "old_orders" }, rows: "rows", links: null, also: [] },
      PREVIEW
    )

    expect(choice.names).toEqual({ "sales.orders": "old_orders", "sales.customers": "customers" })
    expect(choice.links).toBe("copy")
  })

  it("says why a table nobody ticked is in the copy", () => {
    expect(originNote(PREVIEW.tables[1]!)).toBe("a copied table points at it")
    expect(originNote(PREVIEW.tables[0]!)).toBeUndefined()
  })

  it("reads as the copy runs: the tables, then the rows, then the keys", () => {
    const script = copyScript(PREVIEW)

    expect(script.indexOf("CREATE TABLE")).toBeLessThan(script.indexOf("The rows of sales.orders"))
    expect(script.indexOf("The rows of sales.orders")).toBeLessThan(script.indexOf("PRIMARY KEY"))
  })

  it("starts where the catalog stood, then in public, then in the first schema", () => {
    const places = [
      { label: "archive", value: "archive" },
      { label: "public", value: "public" },
    ]

    expect(startingPlace(places, "archive")).toBe("archive")
    expect(startingPlace(places, null)).toBe("public")
    expect(startingPlace(places, "gone")).toBe("public")
    expect(startingPlace([places[0]!], null)).toBe("archive")
    expect(startingPlace([], null)).toBeNull()
  })

  it("names what each table leaves behind", () => {
    expect(leftBehind(PREVIEW)).toEqual(["sales.orders: 2 triggers"])
  })
})
