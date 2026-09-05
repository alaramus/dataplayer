import { describe, expect, it } from "vitest"

import type { AdapterTypeInfo } from "@/client"

import { ALL_CATEGORIES, categoryCounts, searchAdapters } from "./adapterSearch"

function adapterType(overrides: Partial<AdapterTypeInfo> = {}): AdapterTypeInfo {
  return {
    name: "postgres",
    title: "PostgreSQL",
    category: "sql",
  catalog_shape: "levels",
    category_title: "SQL Databases",
    description: "Relational database.",
    capabilities: [{ group: "explore", title: "Browse the catalog" }],
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
})

const TYPES = [POSTGRES, FILES]

describe("searching the adapter catalog", () => {
  it("returns everything for an empty query", () => {
    expect(searchAdapters(TYPES, "")).toEqual(TYPES)
  })

  it("ignores surrounding whitespace and case", () => {
    expect(searchAdapters(TYPES, "  POSTGRE  ")).toEqual([POSTGRES])
  })

  it("finds a type by what it can do, not only by its name", () => {
    // The whole reason capabilities are searched: nothing in "Files" says
    // upload, and a user who wants to upload does not know the type's name.
    expect(searchAdapters(TYPES, "upload")).toEqual([FILES])
  })

  it("finds a type by its description", () => {
    expect(searchAdapters(TYPES, "relational")).toEqual([POSTGRES])
  })

  it("finds a type by its category", () => {
    expect(searchAdapters(TYPES, "storage")).toEqual([FILES])
  })

  it("ranks a match in the title above one in the description", () => {
    const named = adapterType({ name: "duck", title: "Relational Duck" })
    // POSTGRES carries "Relational" in its description only.
    expect(searchAdapters([POSTGRES, named], "relational")).toEqual([named, POSTGRES])
  })

  it("answers with nothing when nothing matches", () => {
    expect(searchAdapters(TYPES, "kafka")).toEqual([])
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
