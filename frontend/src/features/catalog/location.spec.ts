import { describe, expect, it } from "vitest"

import { isPathTrail, locationOf } from "@/features/catalog/location"
import type { CatalogNode } from "@/features/catalog/nodes"

/**
 * A path from the server is a chain of nodes; a catalog level is a trail of
 * crumbs plus a set of ticked groupings. The translation is by role and never
 * by the type of the source — see the spec, P3.
 */

const schema = (name: string): CatalogNode => ({
  kind: "schema",
  id: name,
  name,
  has_children: true,
  is_system: false,
  representations: [],
})

const table = (id: string, name: string): CatalogNode => ({
  kind: "table",
  id,
  name,
  has_children: true,
  is_system: false,
  representations: [{ kind: "table", title: "View as table" }],
})

const directory = (id: string, name: string): CatalogNode => ({
  kind: "directory",
  id,
  name,
  has_children: true,
  representations: [],
})

const file = (id: string, name: string): CatalogNode => ({
  kind: "file",
  id,
  name,
  has_children: false,
  size_bytes: 1,
  representations: [{ kind: "table", title: "View as table" }],
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
      { id: "reports", label: "reports", kind: "directory" },
      { id: "reports/2026", label: "2026", kind: "directory" },
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
    expect(location.crumbs).toEqual([{ id: "sales", label: "sales", kind: "directory" }])
    expect(location.groups).toEqual(["public"])
  })

  it("has no location for an empty path", () => {
    const location = locationOf([])

    expect(location.parentId).toBe(null)
    expect(location.crumbs).toEqual([])
    expect(location.groups).toEqual([])
  })
})

describe("a trail that is a path", () => {
  const root = { id: null, label: "mydb" }

  it("is the root of a connection, whose path is the root itself", () => {
    expect(isPathTrail([root])).toBe(true)
  })

  it("is folders walked into", () => {
    expect(
      isPathTrail([root, { id: "reports", label: "reports", kind: "directory" }])
    ).toBe(true)
  })

  it("is not a section of reports, whose id is an id and not a path", () => {
    // `/pg_dataplayer.timescale.v1` was offered for copying out of the system
    // reports of a database. A node id is opaque outside its adapter.
    expect(
      isPathTrail([root, { id: "pg_dataplayer", label: "System", kind: "report" }])
    ).toBe(false)
  })

  it("is not an archive, whose members are not on disk", () => {
    expect(
      isPathTrail([
        root,
        { id: "backup.zip", label: "backup.zip", kind: "file" },
      ])
    ).toBe(false)
  })
})
