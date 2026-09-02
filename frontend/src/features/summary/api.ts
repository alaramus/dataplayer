import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"

export const nodeSummaryKey = (connectorId: string, nodeId: string) =>
  ["nodeSummary", connectorId, nodeId] as const

/**
 * What one node is, read once and kept for a while.
 *
 * A summary is a stat and a bounded read rather than a page of data, and
 * nothing on this screen changes it, so it is left stale for as long as a
 * relation model is: re-reading it is the panel's own reload button.
 */
export function useNodeSummary(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => nodeSummaryKey(connectorId.value, nodeId.value)),
    queryFn: async () =>
      (
        await ConnectorsService.readNodeSummary({
          path: { connector_id: connectorId.value },
          query: { node_id: nodeId.value },
        })
      ).data,
    staleTime: 5 * 60_000,
  })
}
