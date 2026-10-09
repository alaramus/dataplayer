import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"

export const stateKey = (connectorId: string, nodeId: string) =>
  ["connectors", connectorId, "hypertableDesign", nodeId] as const

/**
 * The hypertable as it is now, read once for each opening of the editor.
 *
 * Never kept: the editor plans against the source and a stale picture would
 * offer to change what is no longer there. Under the connector's key, so a
 * change to the connector drops it too.
 */
export function useHypertableState(connectorId: Ref<string>, nodeId: Ref<string>, open: Ref<boolean>) {
  return useQuery({
    queryKey: computed(() => stateKey(connectorId.value, nodeId.value)),
    queryFn: async () => {
      const response = await ConnectorsService.hypertableDesignState({
        path: { connector_id: connectorId.value },
        body: { node_id: nodeId.value },
      })
      return response.data
    },
    enabled: computed(() => open.value && connectorId.value !== "" && nodeId.value !== ""),
    staleTime: 0,
    gcTime: 0,
    // A refetch replaces the form's draft, so returning to the window must not ask again.
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  })
}
