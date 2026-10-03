import type { SearchRequest } from "@/client"
import type { Panel } from "@/features/workspace/panels"
import type { SearchScope } from "@/features/workspace/state"
import { leavesOf } from "@/shared/workspace"
import type { LayoutNode, NodeId, PanelId } from "@/shared/workspace"

type Place = NonNullable<SearchRequest["only"]>[number]

/** What a scope asks: that connection only, from the level its catalog stood on (D205). */
export function placeOf(scope: SearchScope): Place {
  return { kind: "connection", connector_id: scope.connectorId, node_id: scope.nodeId }
}

/** The most connections a request names as its context (the server's MAX_CONTEXT). */
export const MAX_CONTEXT = 8

/**
 * The connections the person is working with, for the search to ask while
 * typing and first on Enter (D200): the one being looked at, then the others
 * with a catalog open, in the order they were opened, at most eight.
 */
export function contextOf(active: string | null, open: Iterable<string>): string[] {
  const ordered = active === null ? [...open] : [active, ...[...open].filter((id) => id !== active)]
  return [...new Set(ordered)].slice(0, MAX_CONTEXT)
}

type CatalogPanel = Extract<Panel, { kind: "catalog" }>

/**
 * The catalog that has the focus, if one has: a floating one in front, or the
 * tab shown in the section last pressed. Not the catalog merely on screen —
 * a scope is offered for where the person is, not for where a catalog is
 * (D205).
 */
export function focusedCatalog(
  panels: readonly Panel[],
  tree: LayoutNode,
  focusedLeaf: NodeId | null,
  focusedDetached: PanelId | null
): CatalogPanel | null {
  if (focusedDetached !== null) {
    const floating = panels.find((panel) => panel.id === focusedDetached)
    return floating?.kind === "catalog" ? floating : null
  }
  const leaf = leavesOf(tree).find((one) => one.id === focusedLeaf)
  if (leaf === undefined || leaf.activePanel === null) return null
  const shown = panels.find((panel) => panel.id === leaf.activePanel)
  return shown?.kind === "catalog" ? shown : null
}
