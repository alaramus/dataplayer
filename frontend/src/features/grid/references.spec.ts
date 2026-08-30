import { describe, expect, it } from "vitest"

import type { FetchColumn, FetchReference } from "@/client"

import { keyValues, referencesLedBy } from "./references"

const composite: FetchReference = {
  name: "customers_region_fkey",
  columns: ["region_id", "region_code"],
  target_title: "sales.regions",
}
const single: FetchReference = {
  name: "customers_owner_fkey",
  columns: ["owner_id"],
  target_title: "sales.people",
}

function column(name: string): FetchColumn {
  return { name, type: { sql: "text", category: "string" } }
}

describe("where a way out is drawn", () => {
  it("gives a composite key one handle, on its first column", () => {
    const visible = ["region_id", "region_code", "owner_id"]

    expect(referencesLedBy([composite], "region_id", visible)).toEqual([composite])
    expect(referencesLedBy([composite], "region_code", visible)).toEqual([])
  })

  it("moves the handle when the leading column is hidden", () => {
    const visible = ["region_code", "owner_id"]

    expect(referencesLedBy([composite], "region_code", visible)).toEqual([composite])
  })

  it("draws nothing when no column of the key is on screen", () => {
    expect(referencesLedBy([composite], "region_id", ["owner_id"])).toEqual([])
  })

  it("draws every key a column leads", () => {
    const both = [composite, { ...single, columns: ["region_id"] }]

    expect(referencesLedBy(both, "region_id", ["region_id"])).toHaveLength(2)
  })
})

describe("what is sent when it is pressed", () => {
  const columns = [column("region_id"), column("name"), column("region_code")]

  it("takes every column of the key, in the source's own order", () => {
    expect(keyValues(composite, columns, ["7", "Ada", "north"])).toEqual([
      { column: "region_id", value: "7" },
      { column: "region_code", value: "north" },
    ])
  })

  it("sends an absent value as null rather than leaving it out", () => {
    // What an empty key names is the source's answer, so the whole key travels
    // and the source says there is nothing there.
    expect(keyValues(composite, columns, ["7", "Ada", null])).toEqual([
      { column: "region_id", value: "7" },
      { column: "region_code", value: null },
    ])
  })

  it("sends nothing at all when the page lacks a column of the key", () => {
    expect(keyValues(composite, [column("region_id")], ["7"])).toBeNull()
  })
})
