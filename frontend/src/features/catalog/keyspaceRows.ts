import type { FetchResult } from "@/client"

import type { ListNode } from "./nodes"

/**
 * The rows of a catalog that is expanded rather than walked.
 *
 * Some sources are read one level at a time: a PostgreSQL schema holds
 * thousands of relations, and a screen that opened them all at once is a
 * screen nobody scrolls. A Redis key space is not like that — the scan has a
 * ceiling, the tree is already in the colons of the names, and what a key
 * holds is a handful of fields worth seeing beside the key rather than in
 * another tab.
 *
 * So this maps a catalog level, and a node's own contents, onto one tree —
 * the way a JSON viewer opens an object where it stands. Plain functions with
 * no component around them, built on the same `ListNode` the list view uses,
 * so the two cannot disagree about what a node is called or how it is drawn.
 */

/** What a row stands for, which is what decides whether it can be acted on. */
export type TreeRole = "node" | "value" | "more"

export interface TreeRow {
  /** Unique within the tree: a node's own id, or one derived for a value. */
  id: string
  label: string
  /** What the source said about it, drawn after the label in smaller type. */
  caption?: string
  icon: string
  role: TreeRole
  /** The catalog node this row is, for everything that is one. */
  node?: ListNode
  /** Whether expanding it has to ask the server. */
  lazy?: boolean
  children?: TreeRow[]
}

/** Where a value row's id comes from: the node it belongs to, and its place. */
export function valueId(nodeId: string, index: number): string {
  return `${nodeId}#${String(index)}`
}

/**
 * A level's children as tree rows.
 *
 * Everything is lazy, including the leaves: a folder is expanded to see what
 * is under it and a key to see what is in it, and both are asked for at the
 * moment of opening. A node that can be neither is left without the arrow.
 */
export function toTreeRows(nodes: ListNode[]): TreeRow[] {
  return nodes.map((node) => ({
    id: node.id,
    label: node.label,
    caption: node.caption,
    icon: node.icon,
    role: "node",
    node,
    lazy: node.role === "container" || node.role === "group" || node.readable,
  }))
}

/**
 * One page of what a node holds, as rows of the tree.
 *
 * The shape follows the columns rather than the source: one column is a list
 * of values, two are a name and a value, and more are written out as
 * `name=value`, which is what a stream entry is. Nothing here knows what Redis
 * is, which is what lets the same tree serve the next source that wants one.
 */
export function toValueRows(nodeId: string, page: FetchResult): TreeRow[] {
  const rows: TreeRow[] = page.rows.map((row, index) => ({
    id: valueId(nodeId, index),
    label: row[0] ?? "",
    caption: captionOfValue(page, row),
    icon: "chevron_right",
    role: "value",
  }))
  if (page.has_more) {
    rows.push({
      id: valueId(nodeId, page.rows.length),
      // Said rather than left out: a tree that quietly showed the first
      // hundred of a thousand would be a tree that lies about a key.
      label: "…",
      caption: "open it to see the rest",
      icon: "more_horiz",
      role: "more",
    })
  }
  return rows
}

/** What a value row shows after its label, when it has more than one column. */
function captionOfValue(page: FetchResult, row: (string | null)[]): string | undefined {
  if (page.columns.length <= 1) return undefined
  if (page.columns.length === 2) return row[1] ?? ""
  return page.columns
    .slice(1)
    .map((column, index) => `${column.name}=${row[index + 1] ?? ""}`)
    .join(" ")
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
