import { describe, expect, it } from "vitest"

import { toTreeNodes } from "./treeNodes"
import type { CatalogNode } from "./treeNodes"

describe("toTreeNodes", () => {
  it("keeps id and name and marks expandable nodes as lazy", () => {
    const nodes: CatalogNode[] = [
      { kind: "schema", id: "public", name: "public", has_children: true },
    ]

    const [tree] = toTreeNodes(nodes)

    expect(tree.id).toBe("public")
    expect(tree.label).toBe("public")
    expect(tree.lazy).toBe(true)
  })

  it("does not mark a column as lazy", () => {
    const nodes: CatalogNode[] = [
      {
        kind: "column",
        id: "public.users.email",
        name: "email",
        has_children: false,
        data_type: "varchar",
        nullable: true,
      },
    ]

    const [tree] = toTreeNodes(nodes)

    expect(tree.lazy).toBe(false)
  })

  it("shows the data type of a column as the caption", () => {
    const nodes: CatalogNode[] = [
      {
        kind: "column",
        id: "public.users.email",
        name: "email",
        has_children: false,
        data_type: "character varying(255)",
        nullable: false,
      },
    ]

    const [tree] = toTreeNodes(nodes)

    expect(tree.caption).toContain("character varying(255)")
  })

  it("marks a nullable column so the caption differs from a required one", () => {
    const [nullable] = toTreeNodes([
      {
        kind: "column",
        id: "a",
        name: "a",
        has_children: false,
        data_type: "text",
        nullable: true,
      },
    ])
    const [required] = toTreeNodes([
      {
        kind: "column",
        id: "b",
        name: "b",
        has_children: false,
        data_type: "text",
        nullable: false,
      },
    ])

    expect(nullable.caption).not.toBe(required.caption)
  })

  it("shows the row estimate of a table as the caption", () => {
    const [tree] = toTreeNodes([
      {
        kind: "table",
        id: "public.users",
        name: "users",
        has_children: true,
        row_count_estimate: 1234,
      },
    ])

    expect(tree.caption).toContain("1234")
  })

  it("omits the caption when a table has no estimate yet", () => {
    const [tree] = toTreeNodes([
      {
        kind: "table",
        id: "public.users",
        name: "users",
        has_children: true,
        row_count_estimate: null,
      },
    ])

    expect(tree.caption).toBeUndefined()
  })

  it("distinguishes a materialized view from a plain one", () => {
    const [plain] = toTreeNodes([{ kind: "view", id: "v", name: "v", has_children: true }])
    const [materialized] = toTreeNodes([
      { kind: "view", id: "m", name: "m", has_children: true, is_materialized: true },
    ])

    expect(plain.caption).not.toBe(materialized.caption)
  })

  it("gives every kind its own icon", () => {
    const icons = toTreeNodes([
      { kind: "schema", id: "s", name: "s", has_children: true },
      { kind: "table", id: "t", name: "t", has_children: true },
      { kind: "view", id: "v", name: "v", has_children: true },
      {
        kind: "column",
        id: "c",
        name: "c",
        has_children: false,
        data_type: "int",
        nullable: false,
      },
    ]).map((node) => node.icon)

    expect(new Set(icons).size).toBe(4)
  })
})

describe("node kind passthrough", () => {
  it("keeps the kind so callers can tell rows-bearing nodes apart", () => {
    const kinds = toTreeNodes([
      { kind: "schema", id: "s", name: "s", has_children: true },
      { kind: "table", id: "t", name: "t", has_children: true, row_count_estimate: 12 },
    ]).map((node) => node.kind)

    expect(kinds).toEqual(["schema", "table"])
  })

  it("carries the row estimate only for tables", () => {
    const [schema, table] = toTreeNodes([
      { kind: "schema", id: "s", name: "s", has_children: true },
      { kind: "table", id: "t", name: "t", has_children: true, row_count_estimate: 12 },
    ])

    expect(schema.rowEstimate).toBeNull()
    expect(table.rowEstimate).toBe(12)
  })
})
