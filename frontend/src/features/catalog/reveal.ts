import type { Crumb, Location } from "./location"

/** What a catalog stands on and holds, as far as pointing at a node is concerned. */
export interface CatalogHolding {
  currentId: string | null
  selectedGroups: readonly string[]
  /** Showing what a search found rather than the level (D76). */
  searched: boolean
  filter: string
  ticked: number
  /** The ids its list draws now. */
  shown: readonly string[]
}

/**
 * How a catalog asked to show a node does it (D112, D205):
 *
 * - `mark`: the node is on the level it stands on, in sight;
 * - `leave-search`: on that level, behind search results, which it leaves;
 * - `walk`: on another level, and going there loses nothing;
 * - `elsewhere`: on another level, or hidden by a filter, while the catalog
 *   holds a search, a filter or ticks. Going there would wipe them, so another
 *   catalog of the connection opens at the node's level instead.
 */
export type RevealPlan = "mark" | "leave-search" | "walk" | "elsewhere"

/** Whether the catalog already stands where the node lives: its level, its groupings ticked. */
export function standsAt(
  holding: Pick<CatalogHolding, "currentId" | "selectedGroups">,
  location: Location
): boolean {
  return (
    holding.currentId === location.parentId &&
    location.groups.every((id) => holding.selectedGroups.includes(id))
  )
}

export function revealPlan(holding: CatalogHolding, location: Location, nodeId: string): RevealPlan {
  const filtered = holding.filter.trim() !== ""
  if (standsAt(holding, location)) {
    if (holding.searched) return "leave-search"
    return filtered && !holding.shown.includes(nodeId) ? "elsewhere" : "mark"
  }
  return holding.searched || filtered || holding.ticked > 0 ? "elsewhere" : "walk"
}

/**
 * Where a node lives, from the levels above it that its hit names: for a
 * source with no node path — a Redis key — whose tree must still be opened
 * down to it (D205). An ancestor the catalog offers as a grouping is ticked,
 * as a path would have said; every other one is a branch on the way.
 */
export function locationFromAncestors(
  ancestors: readonly { id: string; label: string }[],
  groupIds: readonly string[]
): Location {
  const crumbs: Crumb[] = []
  const groups: string[] = []
  for (const ancestor of ancestors) {
    if (groupIds.includes(ancestor.id)) groups.push(ancestor.id)
    else crumbs.push({ id: ancestor.id, label: ancestor.label })
  }
  return { crumbs, groups, parentId: crumbs[crumbs.length - 1]?.id ?? null }
}
