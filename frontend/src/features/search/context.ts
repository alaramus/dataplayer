import type { BrowserPlace, RecentTarget, SearchRequest } from "@/client"
import { connectionNameOf } from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"
import type { SearchScope } from "@/features/workspace/state"
import { activeCatalogPanel } from "@/features/workspace/activeCatalog"
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

/**
 * The scope the field offers (D205): the focused catalog first, standing where
 * it stands; then the tab being looked at when it names a connection, at its
 * top; then the catalog being looked at.
 *
 * The fallbacks are why closing the last table does not lose the scope: the
 * focus stays on the emptied work column while the catalog is still open, and
 * a scope offered for the focus alone would be gone with the table. A work
 * tab's own title is never its connection's name, so only a fresh name or the
 * panel's connector name labels its scope — never the title.
 */
export function offeredScope(
  panels: readonly Panel[],
  tree: LayoutNode,
  focusedLeaf: NodeId | null,
  focusedDetached: PanelId | null,
  searchFromOf: (panelId: string) => string | null,
  labelOf: (connectorId: string) => string | null
): SearchScope | null {
  const scopeOf = (catalog: Extract<Panel, { kind: "catalog" }>): SearchScope => ({
    connectorId: catalog.connectorId,
    label: labelOf(catalog.connectorId) ?? catalog.title,
    nodeId: searchFromOf(catalog.id),
  })
  const focused = focusedCatalog(panels, tree, focusedLeaf, focusedDetached)
  if (focused !== null) return scopeOf(focused)
  const lookingAt = panelInFocus(panels, tree, focusedLeaf, focusedDetached)
  if (lookingAt !== null) {
    const named = connectionOfPanel(lookingAt, labelOf)
    if (named !== null) return { connectorId: named.connectorId, label: named.label, nodeId: null }
  }
  const activeId = activeCatalogPanel(tree, focusedLeaf)
  const active = activeId === null ? undefined : panels.find((panel) => panel.id === activeId)
  return active !== undefined && active.kind === "catalog" ? scopeOf(active) : null
}

/** The tab being looked at: the floating one in front, or the focused section's active tab. */
function panelInFocus(
  panels: readonly Panel[],
  tree: LayoutNode,
  focusedLeaf: NodeId | null,
  focusedDetached: PanelId | null
): Panel | null {
  if (focusedDetached !== null) return panels.find((panel) => panel.id === focusedDetached) ?? null
  const leaf = leavesOf(tree).find((one) => one.id === focusedLeaf)
  if (leaf === undefined || leaf.activePanel === null) return null
  return panels.find((panel) => panel.id === leaf.activePanel) ?? null
}

/** The connection a tab names, with what the scope chip shows for it. */
function connectionOfPanel(
  panel: Panel,
  labelOf: (connectorId: string) => string | null
): { connectorId: string; label: string } | null {
  // Some panels may stand on no connection at all, so the id is optional.
  const connectorId = "connectorId" in panel ? panel.connectorId : undefined
  if (!connectorId) return null
  const label = labelOf(connectorId) || connectionNameOf(panel)
  return label ? { connectorId, label } : null
}

/**
 * What only the browser knows, sent with a request as hints: what was opened
 * from the search lately (S6) and the open tabs and saved groups (S9). An empty
 * list is left out.
 */
export function hintsOf(
  recent: RecentTarget[],
  browser: BrowserPlace[]
): Pick<SearchRequest, "recent" | "browser"> {
  return { ...(recent.length > 0 ? { recent } : {}), ...(browser.length > 0 ? { browser } : {}) }
}
