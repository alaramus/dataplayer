import { describe, expect, it } from "vitest"

import type { AdapterTypeInfo } from "@/client"

import { ALL_CATEGORIES, categoryCounts, inFoundOrder } from "./adapterSearch"

function adapterType(overrides: Partial<AdapterTypeInfo> = {}): AdapterTypeInfo {
  return {
    name: "postgres",
    title: "PostgreSQL",
    category: "sql",
  catalog_shape: "levels",
    category_title: "SQL Databases",
    description: "Relational database.",
    capabilities: [{ group: "explore", title: "Browse the catalog" }],
    guide: "source-postgres",
    can_see: ["Schemas, tables and views"],
    can_change: ["Table data and columns"],
    cache_windows: { catalog: 30, fetch: 10 },
    options_schema: {},
    ...overrides,
  }
}

const POSTGRES = adapterType()
const FILES = adapterType({
  name: "file",
  title: "Files",
  category: "files",
  category_title: "Files & Storage",
  description: "Your personal storage on this server.",
  capabilities: [
    { group: "explore", title: "Browse the catalog" },
    { group: "manage", title: "Upload files" },
  ],
  guide: "source-file",
  can_see: ["Folders and files"],
  can_change: ["Files and folders: create, upload, rename, delete"],
})

const TYPES = [POSTGRES, FILES]

describe("the order the search found types in", () => {
  it("keeps the search's order and drops a name the catalog does not hold", () => {
    expect(inFoundOrder(TYPES, ["file", "kafka", "postgres"])).toEqual([FILES, POSTGRES])
  })
})

describe("counting the categories", () => {
  it("puts every type under All, first", () => {
    const counts = categoryCounts(TYPES)

    expect(counts[0]).toEqual({ id: ALL_CATEGORIES, title: "All", count: 2 })
  })

  it("names each category once, with the server's own wording", () => {
    const counts = categoryCounts(TYPES).slice(1)

    expect(counts).toEqual([
      { id: "files", title: "Files & Storage", count: 1 },
      { id: "sql", title: "SQL Databases", count: 1 },
    ])
  })

  it("counts the types in a category rather than the types there are", () => {
    const second = adapterType({ name: "duck", title: "DuckDB" })

    const counts = categoryCounts([...TYPES, second])

    expect(counts.find((row) => row.id === "sql")?.count).toBe(2)
  })

  it("leaves out a category no type belongs to", () => {
    expect(categoryCounts([POSTGRES]).map((row) => row.id)).toEqual([ALL_CATEGORIES, "sql"])
  })
})
