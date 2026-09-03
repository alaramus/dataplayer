/**
 * Every change to the layout is a pure function: it takes a tree and returns a
 * new one. Nodes carry no reference to their parent, so a node is addressed by
 * the path that reaches it.
 *
 * The old application mutated nodes in place and kept parent back-pointers,
 * which is why it needed a history of layouts and a command language to undo
 * anything. See the spec, W3.
 */

import type { LayoutNode, LeafNode, NodeId, PanelId, Path, DropZone } from "./model"
import { makeSplit, makeLeaf } from "./model"

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

/** Replace one opaque panel id everywhere without moving its tab. */
export function renamePanel(
  root: LayoutNode,
  oldPanelId: PanelId,
  newPanelId: PanelId
): LayoutNode {
  if (root.kind === "split") {
    return {
      ...root,
      children: root.children.map((child) =>
        renamePanel(child, oldPanelId, newPanelId)
      ),
    }
  }
  if (!root.panels.includes(oldPanelId)) return root
  return {
    ...root,
    panels: root.panels.map((panelId) =>
      panelId === oldPanelId ? newPanelId : panelId
    ),
    activePanel: root.activePanel === oldPanelId ? newPanelId : root.activePanel,
  }
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
    if (root.panels.length === 0) {
      // A pinned section is a column of the screen rather than a container of
      // panels: it outlives the last thing put in it. See the spec, T2.
      if (root.pinned !== true) return null
      return root.activePanel === null ? root : { ...root, activePanel: null }
    }
    if (root.activePanel !== null && root.panels.includes(root.activePanel)) return root
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

/** Normalise, and fall back to the tree we had when nothing would be left. */
function settle(root: LayoutNode, previous: LayoutNode): LayoutNode {
  return normalize(root) ?? previous
}

function withLeaf(
  root: LayoutNode,
  leafId: NodeId,
  change: (leaf: LeafNode) => LayoutNode | null
): LayoutNode {
  const path = pathOfNode(root, leafId)
  if (path === null) return root
  const leaf = nodeAt(root, path)
  if (leaf === null || leaf.kind !== "leaf") return root
  const replaced = replaceAt(root, path, change(leaf))
  return replaced === null ? root : settle(replaced, root)
}

/**
 * Put a panel into a section, at a place in its strip or at the end of it.
 *
 * `at` is where a dragged tab was released — the whole point of dragging one
 * within its own strip, which used to land at the end however carefully it was
 * aimed. Absent for a panel that is merely opened: nobody aimed at anything,
 * and the end is where a new tab belongs.
 */
export function addPanel(
  root: LayoutNode,
  leafId: NodeId,
  panelId: PanelId,
  at?: number
): LayoutNode {
  return withLeaf(root, leafId, (leaf) => {
    if (leaf.panels.includes(panelId)) return { ...leaf, activePanel: panelId }
    const panels = [...leaf.panels]
    panels.splice(at ?? panels.length, 0, panelId)
    return { ...leaf, panels, activePanel: panelId }
  })
}

export function removePanel(root: LayoutNode, panelId: PanelId): LayoutNode | null {
  const path = pathOfPanel(root, panelId)
  if (path === null) return root
  const leaf = nodeAt(root, path)
  if (leaf === null || leaf.kind !== "leaf") return root

  const panels = leaf.panels.filter((id) => id !== panelId)
  // An unpinned section goes with its last panel; a pinned one stays and
  // normalize clears what it thought was active.
  if (panels.length === 0 && leaf.pinned !== true) {
    const replaced = replaceAt(root, path, null)
    return replaced === null ? null : normalize(replaced)
  }

  const next: LeafNode = {
    ...leaf,
    panels,
    activePanel: leaf.activePanel === panelId ? (panels[0] ?? null) : leaf.activePanel,
  }

  const replaced = replaceAt(root, path, next)
  return replaced === null ? null : normalize(replaced)
}

export function activatePanel(root: LayoutNode, panelId: PanelId): LayoutNode {
  const path = pathOfPanel(root, panelId)
  if (path === null) return root
  const leaf = nodeAt(root, path)
  if (leaf === null || leaf.kind !== "leaf") return root
  return settle(replaceAt(root, path, { ...leaf, activePanel: panelId }) ?? root, root)
}

export function setCollapsed(root: LayoutNode, leafId: NodeId, collapsed: boolean): LayoutNode {
  return withLeaf(root, leafId, (leaf) => ({ ...leaf, collapsed }))
}

/**
 * Move the border between `children[before]` and `children[after]`.
 *
 * Two indices rather than one and its successor: a section with nothing to
 * show is off the screen, and the two sections a user sees on either side of a
 * border are then not neighbours in the tree. Everything between them keeps
 * the width it had, which is what brings it back unchanged. See P4.
 *
 * Sizes are percentages and the limit is pixels, so the caller converts: the
 * component that owns the element knows how wide it is, and this function
 * knows nothing about the screen.
 */
export function resizeSplit(
  root: LayoutNode,
  splitId: NodeId,
  beforeIndex: number,
  afterIndex: number,
  delta: number,
  minPercent: number
): LayoutNode {
  const path = pathOfNode(root, splitId)
  if (path === null) return root
  const split = nodeAt(root, path)
  if (split === null || split.kind !== "split") return root

  const before = split.sizes[beforeIndex]
  const after = split.sizes[afterIndex]
  if (before === undefined || after === undefined) return root

  const room = before + after
  const clamped = Math.min(Math.max(before + delta, minPercent), room - minPercent)
  if (!Number.isFinite(clamped) || clamped <= 0) return root

  const sizes = [...split.sizes]
  sizes[beforeIndex] = clamped
  sizes[afterIndex] = room - clamped

  const replaced = replaceAt(root, path, { ...split, sizes })
  // Normalised like every other operation. Resizing cannot on its own leave a
  // tree that needs repair, but an operation that skips the step is the crack
  // W4 exists to close: nothing downstream should have to know which ones do.
  return replaced === null ? root : settle(replaced, root)
}

const DIRECTION_OF: Record<Exclude<DropZone, "center">, "row" | "column"> = {
  left: "row",
  right: "row",
  top: "column",
  bottom: "column",
}

const FIRST: DropZone[] = ["left", "top"]

export function splitLeaf(
  root: LayoutNode,
  leafId: NodeId,
  panelId: PanelId,
  zone: DropZone,
  newLeafId: NodeId,
  at?: number
): LayoutNode {
  if (zone === "center") return addPanel(root, leafId, panelId, at)

  return withLeaf(root, leafId, (leaf) => {
    // The role is inherited and the pin is not. A section with no role takes
    // nothing at all once P1 holds, so the first split would produce a dead
    // corner of the screen; a section that may stay empty would leave a trace
    // behind every split. See P2.
    const arrival = makeLeaf(newLeafId, [panelId], { accepts: leaf.accepts })
    const children = FIRST.includes(zone) ? [arrival, leaf] : [leaf, arrival]
    return makeSplit(`split-${newLeafId}`, DIRECTION_OF[zone], children, [50, 50])
  })
}

/**
 * Take a panel out of wherever it is and put it into a target section.
 *
 * The removal happens first, and it may take the target section with it when
 * the panel was the only thing in it. That is not an error to work around: the
 * gesture had no destination, so nothing happens at all.
 */
export function movePanel(
  root: LayoutNode,
  panelId: PanelId,
  targetLeafId: NodeId,
  zone: DropZone,
  newLeafId: NodeId,
  at?: number
): LayoutNode {
  const without = removePanel(root, panelId)
  if (without === null) return root
  if (pathOfNode(without, targetLeafId) === null) return root
  // The place is an index into the strip the panel has already left, which is
  // what the pointer was over: the tab in the hand is not drawn among them.
  return splitLeaf(without, targetLeafId, panelId, zone, newLeafId, at)
}
