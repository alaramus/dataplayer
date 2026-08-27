import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type {
  DeleteRowsRequest,
  FetchRequest,
  FetchResult,
  InsertRowRequest,
  UpdateCellRequest,
} from "@/client"

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

function useRowsMutation<TBody>(
  connectorId: Ref<string>,
  run: (connectorId: string, body: TBody) => Promise<unknown>
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TBody) => run(connectorId.value, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["rows", connectorId.value] })
    },
  })
}

export function useInsertRow(connectorId: Ref<string>) {
  return useRowsMutation(connectorId, async (id, body: InsertRowRequest) =>
    (
      await ConnectorsService.insertRow({
        path: { connector_id: id },
        body,
      })
    ).data
  )
}

export function useDeleteRows(connectorId: Ref<string>) {
  return useRowsMutation(connectorId, async (id, body: DeleteRowsRequest) =>
    (
      await ConnectorsService.deleteRows({
        path: { connector_id: id },
        body,
      })
    ).data
  )
}
