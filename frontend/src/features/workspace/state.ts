import { inject } from "vue"
import type { InjectionKey, Ref } from "vue"

/**
 * What one panel may ask the workspace to open.
 *
 * Provided by the page: the engine renders a panel with no props of its own,
 * and a panel has no business reaching into the layout.
 */
export interface WorkspaceActions {
  /** The connection whose catalog is open, so a panel can show which it is. */
  activeConnectorId: Readonly<Ref<string | null>>
  openCatalog: (connectorId: string, title: string) => void
  openRows: (connectorId: string, nodeId: string, title: string) => void
}

export const workspaceActionsKey: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(workspaceActionsKey)
  if (actions === undefined) throw new Error("A panel used outside the workspace page")
  return actions
}
