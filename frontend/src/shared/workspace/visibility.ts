import type { LayoutNode } from "./model"
import { leavesOf } from "./tree"

/**
 * Whether a section is on the screen at all.
 *
 * `pinned` keeps a *role* on the screen rather than one particular section:
 * a section split off another inherits the role (P2), so a pinned column can
 * be left holding nothing while its role is served by the section beside it —
 * and an empty view that says "pick a table to read it here" next to an open
 * table promises what has already been done. The engine still reads no role:
 * it compares two opaque strings and counts panels. See P4.
 */
export function isSectionHidden(
  root: LayoutNode,
  node: LayoutNode,
  hasEmptyView: (accepts: string | null) => boolean
): boolean {
  // A split is a box of sections and has nothing of its own to show: it goes
  // when every section in it has gone, or it would hold room open for nothing.
  if (node.kind === "split") {
    return node.children.every((child) => isSectionHidden(root, child, hasEmptyView))
  }
  // A section put aside is not on the screen, so what it holds is not on the
  // screen either: it counts as holding nothing, and the rules below then say
  // what stands in its place — the feature's empty view where there is one,
  // and otherwise the room it was taking, given to the columns that are left.
  if (node.minimized !== true && node.activePanel !== null) return false
  if (!hasEmptyView(node.accepts ?? null)) return true
  // Its role is already being done elsewhere on the screen.
  return leavesOf(root).some(
    (other) =>
      other.id !== node.id &&
      other.accepts === node.accepts &&
      other.minimized !== true &&
      other.activePanel !== null
  )
}
