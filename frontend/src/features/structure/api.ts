import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"

export const relationModelKey = (connectorId: string, nodeId: string) =>
  ["relationModel", connectorId, nodeId] as const

export function useRelationModel(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => relationModelKey(connectorId.value, nodeId.value)),
    queryFn: async () =>
      (
        await ConnectorsService.readRelationModel({
          path: { connector_id: connectorId.value },
          query: { node_id: nodeId.value },
        })
      ).data,
    staleTime: 5 * 60_000,
  })
}
