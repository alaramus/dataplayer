import { describe, expect, it } from "vitest"

import { rowAt, toTreeRows, toValueRows, valueId, withChildren } from "./keyspaceRows"
import type { TreeRow } from "./keyspaceRows"
import type { ListNode } from "./nodes"

function node(over: Partial<ListNode> = {}): ListNode {
  return {
    id: "k:greeting",
    label: "greeting",
    icon: "vpn_key",
    role: "leaf",
    kind: "key",
    readable: true,
    representations: [{ kind: "table", title: "View what it holds" }],
    describable: false,
    summarizable: false,
    system: false,
    ...over,
  }
}

function page(columns: string[], rows: (string | null)[][], hasMore = false) {
  return {
    columns: columns.map((name) => ({
      name,
      type: { sql: name, category: "string" as const },
      sortable: false,
      filter_operators: [],
      editable: false,
      nullable: false,
      insertable: false,
      insert_required: false,
      has_default: false,
    })),
    rows,
    has_more: hasMore,
    row_handles: [],
    references: [],
    update_supported: false,
    insert_supported: false,
    delete_supported: false,
    export_supported: false,
    page_commands: [],
    row_commands: [],
  }
}

describe("a catalog level as rows of a tree", () => {
  it("keeps what the list already decided about a node", () => {
    // Built on the same `ListNode` the list view uses, so the two cannot
    // disagree about what a node is called or how it is drawn.
    const [row] = toTreeRows([node({ caption: "string · 5" })])

    expect(row).toMatchObject({
      id: "k:greeting",
      label: "greeting",
      caption: "string · 5",
      icon: "vpn_key",
      role: "node",
    })
  })

  it("offers to expand a branch and a leaf that can be read", () => {
    const rows = toTreeRows([
      node({ id: "f:cache:", label: "cache:", role: "container", readable: false }),
      node(),
      node({ id: "k:opaque", readable: false, representations: [] }),
    ])

    expect(rows.map((row) => row.lazy)).toEqual([true, true, false])
  })
})

describe("what a node holds, as rows of the same tree", () => {
  it("shows one column as a list of values", () => {
    const rows = toValueRows("k:members", page(["member"], [["ada"], ["alan"]]))

    expect(rows.map((row) => row.label)).toEqual(["ada", "alan"])
    expect(rows.every((row) => row.caption === undefined)).toBe(true)
  })

  it("shows two columns as a name and a value", () => {
    const rows = toValueRows(
      "k:person",
      page(["field", "value"], [["name", "Ada"], ["born", "1815"]])
    )

    expect(rows.map((row) => [row.label, row.caption])).toEqual([
      ["name", "Ada"],
      ["born", "1815"],
    ])
  })

  it("writes more than two columns out, which is what a stream entry is", () => {
    const rows = toValueRows(
      "k:audit",
      page(["id", "who", "what"], [["1-0", "ada", "signed in"]])
    )

    expect(rows[0]?.label).toBe("1-0")
    expect(rows[0]?.caption).toBe("who=ada what=signed in")
  })

  it("says when there is more rather than showing part of it in silence", () => {
    const rows = toValueRows("k:queue", page(["value"], [["one"]], true))

    expect(rows).toHaveLength(2)
    expect(rows[1]?.role).toBe("more")
    expect(rows[1]?.id).toBe(valueId("k:queue", 1))
  })
})

describe("putting a loaded branch into the tree", () => {
  const tree: TreeRow[] = [
    { id: "f:a:", label: "a:", icon: "folder", role: "node", lazy: true },
    {
      id: "f:b:",
      label: "b:",
      icon: "folder",
      role: "node",
      children: [{ id: "k:b:one", label: "one", icon: "vpn_key", role: "node", lazy: true }],
    },
  ]

  it("replaces the branch and stops it asking again", () => {
    const child: TreeRow = { id: "k:a:one", label: "one", icon: "vpn_key", role: "node" }

    const next = withChildren(tree, "f:a:", [child])

    expect(next[0]?.children).toEqual([child])
    expect(next[0]?.lazy).toBe(false)
    // Rebuilt rather than mutated: the tree is state a component holds.
    expect(tree[0]?.children).toBeUndefined()
  })

  it("reaches a branch however deep it is", () => {
    const child: TreeRow = { id: "v", label: "value", icon: "chevron_right", role: "value" }

    const next = withChildren(tree, "k:b:one", [child])

    expect(next[1]?.children?.[0]?.children).toEqual([child])
  })

  it("finds a row anywhere in the tree, and nothing for an id that is not one", () => {
    expect(rowAt(tree, "k:b:one")?.label).toBe("one")
    expect(rowAt(tree, "nowhere")).toBeNull()
    expect(rowAt(tree, null)).toBeNull()
  })
})
