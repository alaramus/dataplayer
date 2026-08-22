/**
 * Every change to the layout is a pure function: it takes a tree and returns a
 * new one. Nodes carry no reference to their parent, so a node is addressed by
 * the path that reaches it.
 *
 * The old application mutated nodes in place and kept parent back-pointers,
 * which is why it needed a history of layouts and a command language to undo
 * anything. See the spec, Р3.
 */

import type { LayoutNode, LeafNode, NodeId, PanelId, Path } from "./model"

export function nodeAt(root: LayoutNode, path: Path): LayoutNode | null {
  let node: LayoutNode = root
  for (const index of path) {
    if (node.kind !== "split") return null
    const child = node.children[index]
    if (child === undefined) return null
    node = child
  }
  return node
}

export function pathOfNode(root: LayoutNode, nodeId: NodeId): Path | null {
  if (root.id === nodeId) return []
  if (root.kind !== "split") return null
  for (const [index, child] of root.children.entries()) {
    const inner = pathOfNode(child, nodeId)
    if (inner !== null) return [index, ...inner]
  }
  return null
}

export function pathOfPanel(root: LayoutNode, panelId: PanelId): Path | null {
  if (root.kind === "leaf") return root.panels.includes(panelId) ? [] : null
  for (const [index, child] of root.children.entries()) {
    const inner = pathOfPanel(child, panelId)
    if (inner !== null) return [index, ...inner]
  }
  return null
}

export function leavesOf(root: LayoutNode): LeafNode[] {
  if (root.kind === "leaf") return [root]
  return root.children.flatMap(leavesOf)
}
