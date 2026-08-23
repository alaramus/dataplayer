import { leavesOf } from "@/shared/workspace"
import type { LayoutNode, NodeId, PanelId } from "@/shared/workspace"

/**
 * Which catalog the user is looking at, read off the layout itself.
 *
 * With one catalog open, "the first catalog panel there is" was the same
 * answer. With several it is the one opened earliest rather than the one being
 * read, so the question is put to the tree: the sections that take catalogs,
 * the focused one first, and its active tab. Nothing is kept beside the tree
 * that could disagree with it. See P7.
 */
export function activeCatalogPanel(tree: LayoutNode, focused: NodeId | null): PanelId | null {
  const columns = leavesOf(tree).filter((leaf) => leaf.accepts === "navigate")
  const preferred = columns.find((leaf) => leaf.id === focused && leaf.activePanel !== null)
  const chosen = preferred ?? columns.find((leaf) => leaf.activePanel !== null)
  return chosen?.activePanel ?? null
}
