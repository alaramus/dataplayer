import { describe, expect, it } from "vitest"

import type { NodeMatch } from "@/client"

import { filterTree, foundTree, rowAt, toTreeRows, withChildren } from "./keyspaceRows"
import type { TreeRow } from "./keyspaceRows"
import type { ListNode } from "./nodes"

function node(over: Partial<ListNode> = {}): ListNode {
  return {
    id: "k0:greeting",
    label: "greeting",
    icon: "vpn_key",
    role: "leaf",
    kind: "key",
    readable: true,
    representations: [{ kind: "table", title: "View what it holds" }],
    describable: false,
    summarizable: false,
    system: false,
    preferred: false,
    holdsNodes: false,
    ...over,
  }
}

describe("a catalog level as rows of a tree", () => {
  it("keeps what the list already decided about a node", () => {
    // Built on the same `ListNode` the list view uses, so the two cannot
    // disagree about what a node is called or how it is drawn.
    const [row] = toTreeRows([node({ caption: "string · 5 characters" })])

    expect(row).toMatchObject({
      id: "k0:greeting",
      label: "greeting",
      caption: "string · 5 characters",
      icon: "vpn_key",
    })
    expect(row?.node.kind).toBe("key")
  })

  it("offers to expand a branch and a grouping, and stops at a leaf", () => {
    // Where the tree stops is where the tab begins: a key is opened, not
    // unfolded, so it carries no arrow at all.
    const rows = toTreeRows([
      node({ id: "d0", label: "db0", role: "group", kind: "database" }),
      node({ id: "f0:cache:", label: "cache:", role: "container", kind: "directory" }),
      node(),
    ])

    expect(rows.map((row) => row.lazy)).toEqual([true, true, false])
  })
})

describe("putting a loaded branch into the tree", () => {
  const tree: TreeRow[] = [
    { id: "f0:a:", label: "a:", icon: "folder", node: node({ id: "f0:a:" }), lazy: true },
    {
      id: "f0:b:",
      label: "b:",
      icon: "folder",
      node: node({ id: "f0:b:" }),
      children: [
        {
          id: "f0:b:one:",
          label: "one:",
          icon: "folder",
          node: node({ id: "f0:b:one:" }),
          lazy: true,
        },
      ],
    },
  ]

  it("replaces the branch and stops it asking again", () => {
    const child: TreeRow = {
      id: "k0:a:one",
      label: "one",
      icon: "vpn_key",
      node: node({ id: "k0:a:one" }),
    }

    const next = withChildren(tree, "f0:a:", [child])

    expect(next[0]?.children).toEqual([child])
    expect(next[0]?.lazy).toBe(false)
    // Rebuilt rather than mutated: the tree is state a component holds.
    expect(tree[0]?.children).toBeUndefined()
  })

  it("reaches a branch however deep it is", () => {
    const child: TreeRow = {
      id: "k0:b:one:two",
      label: "two",
      icon: "vpn_key",
      node: node({ id: "k0:b:one:two" }),
    }

    const next = withChildren(tree, "f0:b:one:", [child])

    expect(next[1]?.children?.[0]?.children).toEqual([child])
  })

  it("finds a row anywhere in the tree, and nothing for an id that is not one", () => {
    expect(rowAt(tree, "f0:b:one:")?.label).toBe("one:")
    expect(rowAt(tree, "nowhere")).toBeNull()
    expect(rowAt(tree, null)).toBeNull()
  })
})

function folder(id: string, label: string, children?: TreeRow[]): TreeRow {
  const [row] = toTreeRows([node({ id, label, role: "container", kind: "directory", readable: false, representations: [], holdsNodes: true })])
  if (row === undefined) throw new Error("no row")
  return children === undefined ? row : { ...row, lazy: false, children }
}

function key(id: string, label: string): TreeRow {
  const [row] = toTreeRows([node({ id, label })])
  if (row === undefined) throw new Error("no row")
  return row
}

function match(name: string, ancestors: [string, string][]): NodeMatch {
  return {
    node: { kind: "key", id: `k0:${name}`, name: name.split(":").pop() ?? name, has_children: false, representations: [], data_type: "string" },
    ancestors: ancestors.map(([node_id, label]) => ({ node_id, name: label })),
  } as NodeMatch
}

describe("filtering what the tree has read", () => {
  const rows = [
    folder("f0:user:", "user:", [key("k0:user:alice", "alice"), key("k0:user:bob", "bob")]),
    folder("f0:order:", "order:"),
    key("k0:greeting", "greeting"),
  ]

  it("keeps a match with the branches above it, and opens them", () => {
    const filtered = filterTree(rows, "ALI")
    expect(filtered.rows.map((row) => row.id)).toEqual(["f0:user:"])
    expect(filtered.rows[0]?.children?.map((row) => row.id)).toEqual(["k0:user:alice"])
    expect(filtered.open).toEqual(["f0:user:"])
  })

  it("keeps a matching branch whole, unopened branches included", () => {
    const filtered = filterTree(rows, "order")
    expect(filtered.rows.map((row) => row.id)).toEqual(["f0:order:"])
    expect(filtered.rows[0]?.lazy).toBe(true)
    expect(filtered.open).toEqual([])
  })

  it("leaves the rows themselves alone while nothing is typed", () => {
    expect(filterTree(rows, "  ").rows).toBe(rows)
  })
})

describe("a search's matches as a tree", () => {
  it("draws each match in the folders below the root, sharing them", () => {
    const built = foundTree(
      [
        match("user:alice", [["d0", "db0"], ["f0:user:", "user:"]]),
        match("user:admin:root", [["d0", "db0"], ["f0:user:", "user:"], ["f0:user:admin:", "admin:"]]),
      ],
      "d0",
      []
    )
    expect(built.rows.map((row) => row.id)).toEqual(["f0:user:"])
    const user = built.rows[0]
    expect(user?.children?.map((row) => row.id)).toEqual(["k0:user:alice", "f0:user:admin:"])
    expect(user?.lazy).toBe(false)
    expect(user?.node.role).toBe("container")
    expect(rowAt(built.rows, "k0:user:admin:root")?.node.kind).toBe("key")
    expect(built.open.sort()).toEqual(["f0:user:", "f0:user:admin:"])
  })

  it("draws a place already read as it was read", () => {
    const known = toTreeRows([node({ id: "d0", label: "db0", kind: "database", role: "group", caption: "4 keys", icon: "storage" })])
    const built = foundTree([match("greeting", [["d0", "db0"]])], null, known)
    expect(built.rows[0]).toMatchObject({ id: "d0", caption: "4 keys", icon: "storage" })
    expect(built.rows[0]?.children?.map((row) => row.id)).toEqual(["k0:greeting"])
  })
})
