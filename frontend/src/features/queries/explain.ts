import type { ExplainNode } from "@/client"

/**
 * A plan read as a list.
 *
 * The tree is what the source answered; the table is the same operations in
 * the order they are drawn, with the depth kept so a row can be indented. One
 * node, two views, one id — which is what makes the two selections the same
 * selection (D65).
 */

export interface PlanRow {
  id: string
  depth: number
  node: ExplainNode
}

export function flatten(node: ExplainNode, depth = 0): PlanRow[] {
  return [
    { id: node.id, depth, node },
    ...(node.children ?? []).flatMap((child) => flatten(child, depth + 1)),
  ]
}

export function nodeById(node: ExplainNode, id: string): ExplainNode | null {
  if (node.id === id) return node
  for (const child of node.children ?? []) {
    const found = nodeById(child, id)
    if (found !== null) return found
  }
  return null
}

/**
 * What one operation is estimated to cost, as a person reads it.
 *
 * Estimates: nothing here was measured, because nothing was run.
 */
export function estimate(node: ExplainNode): string {
  const parts: string[] = []
  if (node.total_cost !== null && node.total_cost !== undefined) {
    parts.push(`cost ${node.total_cost.toFixed(2)}`)
  }
  if (node.rows !== null && node.rows !== undefined) {
    parts.push(`${node.rows} rows`)
  }
  if (node.width !== null && node.width !== undefined) {
    parts.push(`${node.width} bytes wide`)
  }
  return parts.join(" · ")
}

/**
 * The share of the plan's estimated cost this operation carries.
 *
 * A number between 0 and 1, for a bar behind the row: the most expensive
 * operation is what somebody opening a plan is looking for.
 */
export function share(node: ExplainNode, total: number | null | undefined): number {
  if (
    total === null ||
    total === undefined ||
    total <= 0 ||
    node.total_cost === null ||
    node.total_cost === undefined
  ) {
    return 0
  }
  return Math.min(1, node.total_cost / total)
}
