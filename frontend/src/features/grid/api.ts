import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import { freshnessOf } from "@/shared/freshness/freshness"
import type { Freshness } from "@/shared/freshness/freshness"
import type {
  CreateRelationFromSourceRequest,
  DeleteRowsRequest,
  DownloadPageRequest,
  ExportDownloadRequest,
  FetchRequest,
  FetchResult,
  FollowReferenceRequest,
  InsertRowRequest,
  ImportRowsRequest,
  RowCommandRequest,
  UpdateCellRequest,
  UpdateCellsRequest,
} from "@/client"

export const rowsKey = (connectorId: string, request: FetchRequest) =>
  ["rows", connectorId, request] as const

/**
 * A page, and whether it was read or remembered.
 *
 * The two travel together because they are one answer. Kept in a map beside
 * the query cache, the freshness would be a second cache with its own
 * eviction, and the pair would come apart the first time vue-query dropped a
 * page this map still had an opinion about (D105).
 */
export interface RowsPage {
  page: FetchResult
  freshness: Freshness
}

export async function fetchRowsPage(
  connectorId: string,
  request: FetchRequest,
  signal: AbortSignal,
  refresh = false
): Promise<RowsPage> {
  const response = await ConnectorsService.fetchRows({
    path: { connector_id: connectorId },
    query: refresh ? { refresh: true } : {},
    body: request,
    signal,
  })
  return {
    page: response.data,
    freshness: freshnessOf(response.headers as Record<string, unknown>),
  }
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

function useRowsMutation<TBody, TResult>(
  connectorId: Ref<string>,
  run: (connectorId: string, body: TBody) => Promise<TResult>
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

/**
 * Do one source-declared thing to the rows somebody selected (D70).
 *
 * A mutation over the rows for the reason deleting them is: what it did is
 * not in the page that was read a moment ago, so the page is read again.
 * Nothing here knows what any command means — the name and the keys came from
 * the answer that offered them.
 */
export function useRunRowCommand(connectorId: Ref<string>) {
  return useRowsMutation(connectorId, async (id, body: RowCommandRequest) =>
    (
      await ConnectorsService.runRowCommand({
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

export const arrivingReferencesKey = (connectorId: string, nodeId: string) =>
  ["arrivingReferences", connectorId, nodeId] as const

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

/**
 * What points at this relation, asked once for the relation (D110).
 *
 * A query and not a mutation, unlike following one: which keys arrive does not
 * change as the rows are paged, and the answer decides which cells offer the
 * way back at all. A source that cannot search for arriving keys answers 501,
 * which is a fact about the source rather than an error to show — the marks
 * simply do not appear.
 */
export function useArrivingReferences(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => arrivingReferencesKey(connectorId.value, nodeId.value)),
    queryFn: async () =>
      (
        await ConnectorsService.arrivingReferences({
          path: { connector_id: connectorId.value },
          body: { node_id: nodeId.value },
        })
      ).data,
    staleTime: 5 * 60_000,
    retry: false,
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

/**
 * The same two requests, sent to where a copy is kept instead.
 *
 * Two mutations rather than a flag on the two above: what comes back is a
 * different thing — a file for the browser there, a sentence about a file that
 * stayed here — and one call site would have had to know which it was holding.
 */
export function useKeepPage(connectorId: Ref<string>) {
  return useMutation({
    mutationFn: async (body: DownloadPageRequest) =>
      (
        await ConnectorsService.keepPage({
          path: { connector_id: connectorId.value },
          body,
        })
      ).data,
  })
}

export function useKeepRows(connectorId: Ref<string>) {
  return useMutation({
    mutationFn: async (body: ExportDownloadRequest) =>
      (
        await ConnectorsService.keepAllRows({
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

export function useCreateRelationFromSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      connectorId: string
      body: CreateRelationFromSourceRequest
    }) =>
      (
        await ConnectorsService.createRelationFromSource({
          path: { connector_id: input.connectorId },
          body: input.body,
        })
      ).data,
    onSuccess: async (_result, input) => {
      await queryClient.invalidateQueries({ queryKey: ["catalog", input.connectorId] })
    },
  })
}
