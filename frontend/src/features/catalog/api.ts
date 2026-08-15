import { useQueryClient } from "@tanstack/vue-query"

import { ConnectorsService } from "@/client"
import type { CatalogNode } from "./treeNodes"

export const catalogKey = (connectorId: string, nodeId: string | null) =>
  ["catalog", connectorId, nodeId] as const

/**
 * Loader for QTree, whose lazy loading is callback-driven.
 *
 * Goes through queryClient.fetchQuery rather than calling the service
 * directly, so expanded branches still land in the vue-query cache and
 * re-expanding a node does not hit the source again.
 */
export function useCatalogLoader() {
  const queryClient = useQueryClient()

  return async function loadChildren(
    connectorId: string,
    nodeId: string | null
  ): Promise<CatalogNode[]> {
    return queryClient.fetchQuery({
      queryKey: catalogKey(connectorId, nodeId),
      queryFn: async () =>
        (
          await ConnectorsService.readCatalog({
            path: { connector_id: connectorId },
            query: nodeId === null ? {} : { node_id: nodeId },
          })
        ).data,
      staleTime: 60_000,
    })
  }
}
