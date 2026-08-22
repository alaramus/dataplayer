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
  /** The connection whose catalog is open, so a panel can show which it is. */
  activeConnectorId: Readonly<Ref<string | null>>
  openCatalog: (connector: ConnectorPublic) => void
  openRows: (connectorId: string, nodeId: string, title: string) => void
  /**
   * Show the window of one connection, or an empty one for a new connection.
   *
   * Owned by the page rather than by the panel that lists connections: that
   * panel is not rendered while its column is collapsed, and a window inside
   * it would go with it — which is exactly when the catalog needs to open one.
   */
  editConnector: (connectorId: string | null) => void
}

export const workspaceActionsKey: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(workspaceActionsKey)
  if (actions === undefined) throw new Error("A panel used outside the workspace page")
  return actions
}
