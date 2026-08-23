/**
 * What the empty right-hand column has to say, in one plain function.
 *
 * No stage is kept anywhere: it follows from the list of connections and from
 * which catalog is open, both of which already exist. A second record of where
 * the user has got to could disagree with them. See P5.
 */
export type SceneStage = "loading" | "no-connections" | "pick-connection" | "pick-node"

export interface SceneState {
  loading: boolean
  connectorCount: number
  activeConnectorId: string | null
}

export function sceneStage({
  loading,
  connectorCount,
  activeConnectorId,
}: SceneState): SceneStage {
  // An open catalog says where the user is more directly than the list does,
  // and it is still open while the list is being read again.
  if (activeConnectorId !== null) return "pick-node"
  if (loading) return "loading"
  return connectorCount === 0 ? "no-connections" : "pick-connection"
}
