import { inject } from "vue"
import type { InjectionKey, Ref } from "vue"

import type { ConnectorPublic } from "@/client"

/**
 * What one panel may ask the workspace to open.
 *
 * Provided by the page: the engine renders a panel with no props of its own,
 * and a panel has no business reaching into the layout.
 */
export interface WorkspaceActions {
  /** The connection whose catalog is being looked at, of those that are open. */
  activeConnectorId: Readonly<Ref<string | null>>
  /**
   * Every connection that has a catalog open somewhere.
   *
   * Two states rather than one, now that catalogs are as many as were opened:
   * a row says whether it is open at all, and the active one says so fully.
   * See P7.
   */
  openConnectorIds: Readonly<Ref<ReadonlySet<string>>>
  openCatalog: (connector: ConnectorPublic) => void
  /**
   * Show the catalog of a connection and point at one node in it.
   *
   * Opening and coming forward are one thing: a panel is identified by what it
   * shows, so asking for a catalog that is already open brings its tab
   * forward. What is added here is the pointing.
   */
  revealInCatalog: (connectorId: string, nodeId: string, label: string) => void
  /**
   * The node a catalog has just been asked to point at, or nothing.
   *
   * A piece of state rather than a call into the panel: the panel may not have
   * mounted yet — it was opened a moment ago — and a call does not survive
   * that, while something to watch does.
   */
  revealTarget: Readonly<Ref<RevealTarget | null>>
  /**
   * Take the pointing meant for this connection, if the current one is.
   *
   * Taken rather than read: it is acted on once, and a target left behind
   * would point again at the next thing that made the panel re-render.
   */
  takeReveal: (connectorId: string) => RevealTarget | null
  openRows: (request: OpenRowsRequest) => void
  /**
   * Show the window of one connection, or an empty one for a new connection.
   *
   * Owned by the page rather than by the panel that lists connections: that
   * panel is not rendered while its column is collapsed, and a window inside
   * it would go with it — which is exactly when the catalog needs to open one.
   */
  editConnector: (connectorId: string | null) => void
}

/** One node of one connection, to be pointed at once its catalog is showing. */
export interface RevealTarget {
  connectorId: string
  nodeId: string
  /**
   * What the node is called, which the catalog cannot work out on its own.
   *
   * The id is the source's own string and the catalog never takes one apart,
   * so a node that has been deleted since the tab was opened has no name left
   * anywhere else — and "it is gone" is worth saying with the name in it.
   */
  label: string
}

/**
 * What a data tab needs to be opened, which is what it is labelled by.
 *
 * The connection travels with the request rather than being looked up when the
 * tab is drawn: the tab has to name it after a reload too, before the list of
 * connections has been read. See P8.
 */
export interface OpenRowsRequest {
  connectorId: string
  nodeId: string
  /** The node, which is what the tab is called. */
  title: string
  /** Whose it is. In the tooltip of the tab rather than beside its title. */
  connectorName: string
  adapterType: string
}

export const workspaceActionsKey: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(workspaceActionsKey)
  if (actions === undefined) throw new Error("A panel used outside the workspace page")
  return actions
}
