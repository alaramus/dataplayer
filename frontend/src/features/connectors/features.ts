import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import { statusOf } from "@/shared/api/errors"

/**
 * What one saved connection reports about itself, cached by connection.
 *
 * The panel after a check does not read this: a draft has no id, and the
 * check already asked the source (see `sourceFacts.ts`). This is the by-id
 * read behind `/connectors/{id}/features`, and the key is what the three
 * places that change a source invalidate — an action installing an extension
 * must not leave a stale answer behind it.
 */
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
