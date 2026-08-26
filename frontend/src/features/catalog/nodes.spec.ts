import { describe, expect, it } from "vitest"

import { at, first } from "@/shared/testing/collections"
import { groupsOf, roleOfKind, showsPath, toListNodes } from "./nodes"
import type { CatalogNode } from "./nodes"

function group(id: string) {
  return first(toListNodes([{ kind: "schema", id, name: id, has_children: true }]))
}

describe("what the catalog does with a node", () => {
  it("puts a schema in the filter rather than in the list", () => {
    expect(roleOfKind("schema")).toBe("group")
  })

  it("walks into a directory", () => {
    expect(roleOfKind("directory")).toBe("container")
  })

  it("opens a table, a view and a file", () => {
    expect(roleOfKind("table")).toBe("leaf")
    expect(roleOfKind("view")).toBe("leaf")
    expect(roleOfKind("file")).toBe("leaf")
  })

  it("names the grouping a node was listed under, when it was", () => {
    const mapped = first(
      toListNodes([{ kind: "table", id: "sales.orders", name: "orders", has_children: true }], "sales")
    )

    expect(mapped.group).toBe("sales")
  })

  it("leaves the grouping out when a level was listed on its own", () => {
    const mapped = first(toListNodes([{ kind: "table", id: "t", name: "t", has_children: true }]))

    expect(mapped.group).toBeUndefined()
  })
})

describe("groupsOf", () => {
  it("offers the schemas of a level and nothing else", () => {
    const nodes = toListNodes([
      { kind: "schema", id: "public", name: "public", has_children: true },
      { kind: "table", id: "t", name: "t", has_children: true },
    ])

    expect(groupsOf(nodes).map((node) => node.id)).toEqual(["public"])
  })

  it("marks a system schema so it is not the one selected by default", () => {
    const nodes = toListNodes([
      { kind: "schema", id: "pg_catalog", name: "pg_catalog", has_children: true, is_system: true },
      { kind: "schema", id: "public", name: "public", has_children: true },
    ])

    expect(at(nodes, 0).system).toBe(true)
    expect(at(nodes, 1).system).toBe(false)
  })
})

describe("toListNodes", () => {
  it("offers structure for a relation and not for a file", () => {
    expect(
      first(
        toListNodes([
          { kind: "table", id: "public.orders", name: "orders", has_children: false },
        ])
      ).describable
    ).toBe(true)
    expect(
      first(
        toListNodes([{ kind: "view", id: "public.v", name: "v", has_children: false }])
      ).describable
    ).toBe(true)
    expect(
      first(
        toListNodes([
          {
            kind: "file",
            id: "a.csv",
            name: "a.csv",
            has_children: false,
            size_bytes: 1,
            content_kind: "table",
          },
        ])
      ).describable
    ).toBe(false)
  })

  it("keeps id and name", () => {
    const nodes: CatalogNode[] = [
      { kind: "schema", id: "public", name: "public", has_children: true },
    ]

    const node = first(toListNodes(nodes))

    expect(node.id).toBe("public")
    expect(node.label).toBe("public")
  })

  it("shows the row estimate of a table as the caption", () => {
    const node = first(
      toListNodes([
        {
          kind: "table",
          id: "public.users",
          name: "users",
          has_children: true,
          row_count_estimate: 1234,
        },
      ])
    )

    expect(node.caption).toContain("1234")
  })

  it("omits the caption when a table has no estimate yet", () => {
    const node = first(
      toListNodes([
        {
          kind: "table",
          id: "public.users",
          name: "users",
          has_children: true,
          row_count_estimate: null,
        },
      ])
    )

    expect(node.caption).toBeUndefined()
  })

  it("distinguishes a materialized view from a plain one", () => {
    const plain = first(toListNodes([{ kind: "view", id: "v", name: "v", has_children: true }]))
    const materialized = first(
      toListNodes([{ kind: "view", id: "m", name: "m", has_children: true, is_materialized: true }])
    )

    expect(plain.caption).not.toBe(materialized.caption)
  })

  it("gives every visible kind its own icon", () => {
    const icons = toListNodes([
      { kind: "schema", id: "s", name: "s", has_children: true },
      { kind: "table", id: "t", name: "t", has_children: true },
      { kind: "view", id: "v", name: "v", has_children: true },
      { kind: "directory", id: "d", name: "d", has_children: true },
    ]).map((node) => node.icon)

    expect(new Set(icons).size).toBe(4)
  })

  it("carries the row estimate only for tables", () => {
    const mapped = toListNodes([
      { kind: "schema", id: "s", name: "s", has_children: true },
      { kind: "table", id: "t", name: "t", has_children: true, row_count_estimate: 12 },
    ])

    expect(at(mapped, 0).rowEstimate).toBeNull()
    expect(at(mapped, 1).rowEstimate).toBe(12)
  })
})

describe("file sources", () => {
  it("labels a directory and does not call it readable", () => {
    const node = first(
      toListNodes([{ kind: "directory", id: "reports", name: "reports", has_children: true }])
    )

    expect(node.label).toBe("reports")
    expect(node.role).toBe("container")
    expect(node.readable).toBe(false)
  })

  it("shows the size of a file as the caption", () => {
    const node = first(
      toListNodes([
        {
          kind: "file",
          id: "reports/q3.csv",
          name: "q3.csv",
          has_children: false,
          size_bytes: 2048,
          content_kind: "table",
        },
      ])
    )

    expect(node.caption).toContain("2")
    expect(node.caption).toMatch(/KB/i)
  })

  it("marks a readable file as readable and an opaque one as not", () => {
    const mapped = toListNodes([
      {
        kind: "file",
        id: "a.csv",
        name: "a.csv",
        has_children: false,
        size_bytes: 1,
        content_kind: "table",
      },
      {
        kind: "file",
        id: "b.txt",
        name: "b.txt",
        has_children: false,
        size_bytes: 1,
        content_kind: "text",
      },
      {
        kind: "file",
        id: "c.png",
        name: "c.png",
        has_children: false,
        size_bytes: 1,
        content_kind: "opaque",
      },
    ])

    expect(at(mapped, 0).readable).toBe(true)
    expect(at(mapped, 1).readable).toBe(true)
    expect(at(mapped, 2).readable).toBe(false)
  })

  it("has no row estimate for a file: counting rows means reading it", () => {
    const node = first(
      toListNodes([
        {
          kind: "file",
          id: "a.csv",
          name: "a.csv",
          has_children: false,
          size_bytes: 1,
          content_kind: "table",
        },
      ])
    )

    expect(node.rowEstimate).toBeNull()
  })

  it("tells the three kinds of file apart by icon", () => {
    const icons = toListNodes([
      {
        kind: "file",
        id: "a.csv",
        name: "a.csv",
        has_children: false,
        size_bytes: 1,
        content_kind: "table",
      },
      {
        kind: "file",
        id: "b.txt",
        name: "b.txt",
        has_children: false,
        size_bytes: 1,
        content_kind: "text",
      },
      {
        kind: "file",
        id: "c.png",
        name: "c.png",
        has_children: false,
        size_bytes: 1,
        content_kind: "opaque",
      },
    ]).map((node) => node.icon)

    expect(new Set(icons).size).toBe(3)
  })

  it("marks a table and a view as readable and a schema as not", () => {
    const mapped = toListNodes([
      { kind: "table", id: "t", name: "t", has_children: true },
      { kind: "view", id: "v", name: "v", has_children: true },
      { kind: "schema", id: "s", name: "s", has_children: true },
    ])

    expect(at(mapped, 0).readable).toBe(true)
    expect(at(mapped, 1).readable).toBe(true)
    expect(at(mapped, 2).readable).toBe(false)
  })

  it("shows where we are once a step has been taken", () => {
    expect(showsPath(2, [group("public")])).toBe(true)
  })

  it("shows the path at the top of a level that offers no groupings", () => {
    // A personal directory: nothing to filter by, so the head has room for
    // the path and it is there before the first step rather than appearing
    // on it. Read off what the level holds, never off the type of source.
    expect(showsPath(1, [])).toBe(true)
  })

  it("hides a path of one step next to a choice of groupings", () => {
    // A database at its root: the head says which schema is on, and a path
    // of one step beside it would say nothing.
    expect(showsPath(1, [group("public")])).toBe(false)
  })
})
