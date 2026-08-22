import type { LayoutNode, NodeId, PanelId } from "./model"
import { leavesOf, pathOfNode } from "./tree"

/**
 * Which section a newly opened panel belongs in.
 *
 * Read from the tree itself rather than from a record of where panels used to
 * live: a record can disagree with the tree, and the tree cannot disagree with
 * itself. See the spec, W11.
 */
export function leafForKind(
  root: LayoutNode,
  kindOfPanel: (panelId: PanelId) => string | null,
  kind: string,
  focusedLeafId: NodeId | null
): NodeId | null {
  const leaves = leavesOf(root)
  if (leaves.length === 0) return null

  const sameKind = leaves.find((leaf) => leaf.panels.some((id) => kindOfPanel(id) === kind))
  if (sameKind !== undefined) return sameKind.id

  if (focusedLeafId !== null && pathOfNode(root, focusedLeafId) !== null) return focusedLeafId

  let largest = leaves[0]
  if (largest === undefined) return null
  let largestWeight = weightOf(root, largest.id)
  for (const leaf of leaves.slice(1)) {
    const weight = weightOf(root, leaf.id)
    if (weight > largestWeight) {
      largest = leaf
      largestWeight = weight
    }
  }
  return largest.id
}

/** The share of the whole area a section occupies: its sizes multiplied down. */
function weightOf(root: LayoutNode, leafId: NodeId): number {
  const path = pathOfNode(root, leafId)
  if (path === null) return 0

  let node: LayoutNode = root
  let weight = 1
  for (const index of path) {
    if (node.kind !== "split") break
    weight *= (node.sizes[index] ?? 0) / 100
    const child = node.children[index]
    if (!child) break
    node = child
  }
  return weight
}
