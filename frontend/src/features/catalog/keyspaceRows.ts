import type { Ancestor, NodeMatch } from "@/client"

import { toListNodes } from "./nodes"
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

/**
 * What the filter leaves of the rows already read, and the branches to open.
 *
 * The list's rule (a name holding the typed text, case-folded), over what has
 * been loaded: a row stays when its name matches, whole with whatever is read
 * under it, and a branch stays for a match somewhere below it — and is opened,
 * since that match is what it stayed for. What nobody has opened yet is the
 * search's to find.
 */
export function filterTree(
  rows: TreeRow[],
  text: string
): { rows: TreeRow[]; open: string[] } {
  const needle = text.trim().toLowerCase()
  if (needle === "") return { rows, open: [] }
  const open: string[] = []
  const walk = (level: TreeRow[]): TreeRow[] =>
    level.flatMap((row) => {
      if (row.label.toLowerCase().includes(needle)) return [row]
      const kept = walk(row.children ?? [])
      if (kept.length === 0) return []
      open.push(row.id)
      return [{ ...row, children: kept }]
    })
  return { rows: walk(rows), open }
}

/**
 * A search's matches as a tree of their own, each in the folders it lies in.
 *
 * The source names the ancestors of every match (D91); the ones from the
 * tree's root down are drawn, as rows that hold only what was found. A place
 * already read keeps the row it was read as, so a database is still drawn as
 * one; a place nobody opened yet is drawn as the folder it is.
 */
export function foundTree(
  matches: readonly NodeMatch[],
  rootId: string | null,
  known: TreeRow[]
): { rows: TreeRow[]; open: string[] } {
  const top: TreeRow[] = []
  const byId = new Map<string, TreeRow>()
  for (const match of matches) {
    const [found] = toTreeRows(toListNodes([match.node]))
    if (found === undefined || byId.has(found.id)) continue
    const ancestors = match.ancestors ?? []
    const start = ancestors.findIndex((one) => one.node_id === rootId) + 1
    let siblings = top
    for (const ancestor of ancestors.slice(start)) {
      let row = byId.get(ancestor.node_id)
      if (row === undefined) {
        const node = rowAt(known, ancestor.node_id)?.node ?? placeOf(ancestor)
        row = { id: node.id, label: node.label, caption: node.caption, icon: node.icon, node, children: [] }
        byId.set(row.id, row)
        siblings.push(row)
      }
      // A folder that matched itself and also holds a match: it shows what
      // was found in it, as every other place here does.
      row.children ??= []
      row.lazy = false
      siblings = row.children
    }
    byId.set(found.id, found)
    siblings.push(found)
  }
  return { rows: top, open: [...byId.values()].filter((row) => row.children?.length).map((row) => row.id) }
}

function placeOf(ancestor: Ancestor): ListNode {
  const [node] = toListNodes([
    { kind: "directory", id: ancestor.node_id, name: ancestor.name, has_children: true, representations: [] },
  ])
  if (node === undefined) throw new Error("A place became no row")
  return node
}
