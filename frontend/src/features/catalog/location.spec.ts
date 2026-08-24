import { describe, expect, it } from "vitest"

import { locationOf } from "@/features/catalog/location"
import type { CatalogNode } from "@/features/catalog/nodes"

/**
 * A path from the server is a chain of nodes; a catalog level is a trail of
 * crumbs plus a set of ticked groupings. The translation is by role and never
 * by the type of the source — see the spec, Р3.
 */

const schema = (name: string): CatalogNode => ({
  kind: "schema",
  id: name,
  name,
  has_children: true,
  is_system: false,
})

const table = (id: string, name: string): CatalogNode => ({
  kind: "table",
  id,
  name,
  has_children: true,
  is_system: false,
})

const directory = (id: string, name: string): CatalogNode => ({
  kind: "directory",
  id,
  name,
  has_children: true,
})

const file = (id: string, name: string): CatalogNode => ({
  kind: "file",
  id,
  name,
  has_children: false,
  size_bytes: 1,
  content_kind: "table",
})

describe("locationOf", () => {
  it("turns a schema above a table into a ticked grouping on the root", () => {
    const location = locationOf([schema("public"), table("public.users", "users")])

    expect(location.parentId).toBe(null)
    expect(location.crumbs).toEqual([])
    expect(location.groups).toEqual(["public"])
  })

  it("turns directories above a file into a trail of crumbs", () => {
    const location = locationOf([
      directory("reports", "reports"),
      directory("reports/2026", "2026"),
      file("reports/2026/q3.csv", "q3.csv"),
    ])

    expect(location.parentId).toBe("reports/2026")
    expect(location.crumbs).toEqual([
      { id: "reports", label: "reports" },
      { id: "reports/2026", label: "2026" },
    ])
    expect(location.groups).toEqual([])
  })

  it("puts a node with nothing above it on the root", () => {
    const location = locationOf([file("notes.txt", "notes.txt")])

    expect(location.parentId).toBe(null)
    expect(location.crumbs).toEqual([])
    expect(location.groups).toEqual([])
  })

  it("stands on the last container and ticks the grouping below it", () => {
    // A source with levels of its own above a grouping — a database holding
    // schemas holding tables. No source does this today; the rule covers it
    // without a branch of its own.
    const location = locationOf([
      directory("sales", "sales"),
      schema("public"),
      table("sales.public.users", "users"),
    ])

    expect(location.parentId).toBe("sales")
    expect(location.crumbs).toEqual([{ id: "sales", label: "sales" }])
    expect(location.groups).toEqual(["public"])
  })

  it("has no location for an empty path", () => {
    const location = locationOf([])

    expect(location.parentId).toBe(null)
    expect(location.crumbs).toEqual([])
    expect(location.groups).toEqual([])
  })
})
