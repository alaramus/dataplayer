import type { ListNode } from "./nodes"

/**
 * The rows of a catalog that is expanded rather than walked: a key space is
 * bounded and its tree is already in the colons of the names.
 *
 * The tree stops at the nodes, because showing the first rows of a key inside
 * it gave one value two places to be read in. Built on the `ListNode` the list
 * view uses, so the two cannot disagree about what a node is called.
 */

export interface TreeRow {
  id: string
  label: string
  /** What the source said about it, drawn after the label in smaller type. */
  caption?: string
  icon: string
  /** The catalog node this row stands for. */
  node: ListNode
  /** Whether expanding it has to ask the server. */
  lazy?: boolean
  children?: TreeRow[]
}

/**
 * A level's children as tree rows.
 *
 * A branch is lazy and a leaf is not: what is under a folder is asked for at
 * the moment it is opened, and a key has nothing under it — it is opened in a
 * tab instead.
 */
export function toTreeRows(nodes: ListNode[]): TreeRow[] {
  return nodes.map((node) => ({
    id: node.id,
    label: node.label,
    caption: node.caption,
    icon: node.icon,
    node,
    lazy: node.role === "container" || node.role === "group",
  }))
}

/**
 * The rows of a tree with one node's children put in place.
 *
 * Rebuilt rather than mutated: the tree is state a component holds, and a
 * lazily loaded branch that was assigned into an existing object would be a
 * change Vue has to be told about by hand.
 */
export function withChildren(
  rows: TreeRow[],
  id: string,
  children: TreeRow[]
): TreeRow[] {
  return rows.map((row) => {
    if (row.id === id) return { ...row, children, lazy: false }
    if (row.children === undefined) return row
    return { ...row, children: withChildren(row.children, id, children) }
  })
}

/** The row one id names, wherever it is in the tree. */
export function rowAt(rows: TreeRow[], id: string | null): TreeRow | null {
  if (id === null) return null
  for (const row of rows) {
    if (row.id === id) return row
    const found = rowAt(row.children ?? [], id)
    if (found !== null) return found
  }
  return null
}
