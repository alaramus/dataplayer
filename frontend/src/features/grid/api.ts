import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type { FetchRequest, FetchResult, UpdateCellRequest } from "@/client"

export const rowsKey = (connectorId: string, request: FetchRequest) =>
  ["rows", connectorId, request] as const

export async function fetchRowsPage(
  connectorId: string,
  request: FetchRequest,
  signal: AbortSignal
): Promise<FetchResult> {
  return (
    await ConnectorsService.fetchRows({
      path: { connector_id: connectorId },
      body: request,
      signal,
    })
  ).data
}

export function useRowsPage(connectorId: Ref<string>, request: Readonly<Ref<FetchRequest>>) {
  return useQuery({
    queryKey: computed(() => rowsKey(connectorId.value, request.value)),
    queryFn: ({ signal }) => fetchRowsPage(connectorId.value, request.value, signal),
  })
}

export function useUpdateCell(connectorId: Ref<string>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: UpdateCellRequest) =>
      (
        await ConnectorsService.updateCell({
          path: { connector_id: connectorId.value },
          body,
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["rows", connectorId.value] })
    },
  })
}
