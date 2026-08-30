import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type { ContentRequest } from "@/client"

export const contentKey = (connectorId: string, request: ContentRequest) =>
  ["content", connectorId, request] as const

export function useContent(connectorId: Ref<string>, request: Readonly<Ref<ContentRequest>>) {
  return useQuery({
    queryKey: computed(() => contentKey(connectorId.value, request.value)),
    queryFn: async ({ signal }) =>
      (
        await ConnectorsService.readContent({
          path: { connector_id: connectorId.value },
          body: request.value,
          signal,
        })
      ).data,
  })
}
