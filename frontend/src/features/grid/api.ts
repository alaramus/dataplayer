import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type {
  DeleteRowsRequest,
  DownloadPageRequest,
  ExportDownloadRequest,
  FetchRequest,
  FetchResult,
  FollowReferenceRequest,
  InsertRowRequest,
  ImportRowsRequest,
  UpdateCellRequest,
  UpdateCellsRequest,
} from "@/client"

export const rowsKey = (connectorId: string, request: FetchRequest) =>
  ["rows", connectorId, request] as const

export async function fetchRowsPage(
  connectorId: string,
  request: FetchRequest,
  signal: AbortSignal,
  refresh = false
): Promise<FetchResult> {
  return (
    await ConnectorsService.fetchRows({
      path: { connector_id: connectorId },
      query: refresh ? { refresh: true } : {},
      body: request,
      signal,
    })
  ).data
}

export function useRowsPage(
  connectorId: Ref<string>,
  request: Readonly<Ref<FetchRequest>>,
  /**
   * Asked once per fetch, and expected to consume what it reports. A standing
   * flag would mark whichever fetch happens to start next as an explicit
   * reload — including one for a different page the user asked for meanwhile.
   */
  takeRefresh?: () => boolean
) {
  return useQuery({
    queryKey: computed(() => rowsKey(connectorId.value, request.value)),
    queryFn: ({ signal }) =>
      fetchRowsPage(connectorId.value, request.value, signal, takeRefresh?.() === true),
  })
}

/**
 * Forget one page, so the next read of it is a read and not a memory.
 *
 * Recovering from a query the source refused means asking what the relation
 * holds now. An answer already in the client cache is the answer from before
 * whatever changed, and judging by it decides nothing.
 */
export function useForgetRowsPage(connectorId: Ref<string>) {
  const queryClient = useQueryClient()
  return (request: FetchRequest) =>
    queryClient.removeQueries({
      queryKey: rowsKey(connectorId.value, request),
      exact: true,
    })
}

export function useUpdateCells(connectorId: Ref<string>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: UpdateCellsRequest) =>
      (
        await ConnectorsService.updateCells({
          path: { connector_id: connectorId.value },
          body,
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["rows", connectorId.value] })
    },
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

/**
 * Ask the source where one foreign key of one row leads.
 *
 * A mutation rather than a query although it changes nothing: it is a request
 * made when a button is pressed, whose answer is acted on once and never
 * shown again, so there is nothing for a cache key to be about.
 */
export function useFollowReference(connectorId: Ref<string>) {
  return useMutation({
    mutationFn: async (body: FollowReferenceRequest) =>
      (
        await ConnectorsService.followReference({
          path: { connector_id: connectorId.value },
          body,
        })
      ).data,
  })
}

export function useDownloadPage(connectorId: Ref<string>) {
  return useMutation({
    mutationFn: async (body: DownloadPageRequest) => {
      const response = await ConnectorsService.downloadPage({
        path: { connector_id: connectorId.value },
        body,
        responseType: "blob",
      })
      return {
        blob: response.data,
        disposition: response.headers["content-disposition"] as string | undefined,
      }
    },
  })
}

export function useExportRows(connectorId: Ref<string>) {
  return useMutation({
    mutationFn: async (body: ExportDownloadRequest) =>
      (
        await ConnectorsService.exportAllRows({
          path: { connector_id: connectorId.value },
          body,
        })
      ).data,
  })
}

export function useImportRows(connectorId: Ref<string>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: ImportRowsRequest) =>
      (
        await ConnectorsService.importRows({
          path: { connector_id: connectorId.value },
          body,
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["rows", connectorId.value] })
    },
  })
}
