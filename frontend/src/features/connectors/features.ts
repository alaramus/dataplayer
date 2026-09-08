import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import { statusOf } from "@/shared/api/errors"

export const sourceFeaturesKey = (connectorId: string) =>
  ["connectors", connectorId, "features"] as const

export function useSourceFeatures(connectorId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => sourceFeaturesKey(connectorId.value)),
    queryFn: async () => {
      try {
        return (await ConnectorsService.readSourceFeatures({
          path: { connector_id: connectorId.value },
        })).data
      } catch (cause) {
        if (statusOf(cause) === 501) return null
        throw cause
      }
    },
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  })
}
