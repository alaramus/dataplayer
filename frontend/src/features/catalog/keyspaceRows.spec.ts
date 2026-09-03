import { describe, expect, it } from "vitest"

import { rowAt, toTreeRows, withChildren } from "./keyspaceRows"
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
