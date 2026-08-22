/**
 * Every change to the layout is a pure function: it takes a tree and returns a
 * new one. Nodes carry no reference to their parent, so a node is addressed by
 * the path that reaches it.
 *
 * The old application mutated nodes in place and kept parent back-pointers,
 * which is why it needed a history of layouts and a command language to undo
 * anything. See the spec, W3.
 */

import type { LayoutNode, LeafNode, NodeId, PanelId, Path } from "./model"
import { makeSplit } from "./model"

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

/**
 * Put `node` where `path` points, or remove what is there when `node` is null.
 *
 * Nothing is normalised here: the caller performs one edit and then calls
 * normalize once, so a tree is never observed half-changed.
 */
export function replaceAt(
  root: LayoutNode,
  path: Path,
  node: LayoutNode | null
): LayoutNode | null {
  if (path.length === 0) return node
  if (root.kind !== "split") return root

  const firstIndex = path[0]
  if (firstIndex === undefined) return root
  const child = root.children[firstIndex]
  if (child === undefined) return root

  const rest = path.slice(1)
  const replacement = replaceAt(child, rest, node)
  const children = [...root.children]
  const sizes = [...root.sizes]

  if (replacement === null) {
    children.splice(firstIndex, 1)
    sizes.splice(firstIndex, 1)
  } else {
    children[firstIndex] = replacement
  }

  if (children.length === 0) return null
  return makeSplit(root.id, root.direction, children, sizes)
}

/**
 * Bring a tree to its canonical shape.
 *
 * Called after every edit, so no other function has to worry about an empty
 * leaf, a split of one, or sizes that no longer add up. The old application
 * had none of this, which is why it needed sections marked `fake` to stand in
 * for nodes it could not remove.
 */
export function normalize(root: LayoutNode): LayoutNode | null {
  if (root.kind === "leaf") {
    if (root.panels.length === 0) return null
    if (root.panels.includes(root.activePanel)) return root
    const firstPanel = root.panels[0]
    if (firstPanel === undefined) return null
    return { ...root, activePanel: firstPanel }
  }

  const children: LayoutNode[] = []
  const sizes: number[] = []

  for (const [index, child] of root.children.entries()) {
    const kept = normalize(child)
    if (kept === null) continue
    const size = root.sizes[index] ?? 0
    // A nested split running the same way is the same set of borders drawn
    // twice: its children join the parent, sharing the slot it occupied.
    if (kept.kind === "split" && kept.direction === root.direction) {
      const total = kept.sizes.reduce((sum, value) => sum + value, 0) || 1
      for (const [innerIndex, inner] of kept.children.entries()) {
        children.push(inner)
        sizes.push((size * (kept.sizes[innerIndex] ?? 0)) / total)
      }
      continue
    }
    children.push(kept)
    sizes.push(size)
  }

  if (children.length === 0) return null
  if (children.length === 1) {
    const onlyChild = children[0]
    if (onlyChild !== undefined) return onlyChild
  }

  const total = sizes.reduce((sum, value) => sum + value, 0)
  const scaled =
    total > 0 ? sizes.map((value) => (value * 100) / total) : sizes.map(() => 100 / sizes.length)

  return makeSplit(root.id, root.direction, children, scaled)
}
