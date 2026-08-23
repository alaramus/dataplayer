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
  /** Whose it is, said quietly beside the name. */
  connectorName: string
  adapterType: string
}

export const workspaceActionsKey: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(workspaceActionsKey)
  if (actions === undefined) throw new Error("A panel used outside the workspace page")
  return actions
}
