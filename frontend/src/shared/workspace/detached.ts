import { makeLeaf, makeSplit } from "./model"
import type { LayoutNode, NodeId, PanelId } from "./model"
import { addPanel, leavesOf, normalize, setCollapsed } from "./tree"

export interface DetachedPanel {
  panelId: PanelId
  leafId: NodeId
  at: number
  accepts: string
  /** Stable even when persistence has to reconstruct a missing section. */
  fallbackLeafId: NodeId
}

/** The same return rule is used by the button and the persisted layout. */
export function returnPanel(tree: LayoutNode, detached: DetachedPanel): LayoutNode {
  const leaves = leavesOf(tree)
  const target = leaves.find((leaf) => leaf.id === detached.leafId && leaf.accepts === detached.accepts)
    ?? leaves.find((leaf) => leaf.accepts === detached.accepts)
  if (target !== undefined) {
    return setCollapsed(addPanel(tree, target.id, detached.panelId, detached.at), target.id, false)
  }
  const arrival = makeLeaf(detached.fallbackLeafId, [detached.panelId], { accepts: detached.accepts })
  const split = makeSplit(`split-${detached.fallbackLeafId}`, "row", [tree, arrival], [70, 30])
  return normalize(split) ?? split
}

export function dockedLayout(tree: LayoutNode, detached: readonly DetachedPanel[]): LayoutNode {
  return detached.reduce(returnPanel, tree)
}
