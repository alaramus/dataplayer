import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { QueriesService } from "@/client"
import type {
  DeleteEverything,
  DeleteOlderThan,
  DeleteSelected,
  ExplainStart,
  GenerateQueryRequest,
  TransactionStart,
  PrepareRequest,
  QueryMetadataRequest,
  RunStart,
  SnapshotDownloadRequest,
  SnapshotPageRequest,
} from "@/client"

/** One, several, older than a day, or the lot — and nothing else. */
export type RunDeletion =
  | ({ kind: "selected" } & DeleteSelected)
  | ({ kind: "older" } & DeleteOlderThan)
  | ({ kind: "all" } & DeleteEverything)

/**
 * Running something, watching it, and reading what it captured.
 *
 * A run is server state like everything else (D6), with one difference worth
 * naming: it changes on its own. The socket says when, and this is the reading
 * — the route stays the authority and the poll below is the fallback for a
 * message that never arrives (D64).
 */

export const runKey = (runId: string) => ["queries", "runs", runId] as const
export const historyKey = (documentId: string | null, search: string) =>
  ["queries", "history", documentId ?? "any", search] as const
export const resultKey = (resultId: string, view: unknown, offset: number, limit: number) =>
  ["queries", "results", resultId, JSON.stringify(view), offset, limit] as const

/** States a run may still leave; anything else is over. */
const LIVE = new Set(["accepted", "running", "cancelling"])

export function usePrepareQuery() {
  return useMutation({
    mutationFn: async (body: PrepareRequest) =>
      (await QueriesService.prepareText({ body })).data,
  })
}

export function useQueryProfile(connectorId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(connectorId))
  return useQuery({
    queryKey: computed(() => ["queries", "profile", id.value ?? "none"] as const),
    queryFn: async () =>
      (await QueriesService.readProfile({ path: { connector_id: id.value as string } }))
        .data,
    enabled: computed(() => id.value !== null),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
}

export function useStartRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: RunStart) =>
      (await QueriesService.startRun({ body })).data,
    onSuccess: async (run) => {
      queryClient.setQueryData(runKey(run.id), run)
      await queryClient.invalidateQueries({ queryKey: ["queries", "history"] })
    },
  })
}

/**
 * One run, re-read while it is still going.
 *
 * Polling as well as the socket: a message that is missed must not leave a
 * console waiting for ever, and the interval stops as soon as the run is over.
 */
export function useRun(runId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(runId))
  return useQuery({
    queryKey: computed(() => runKey(id.value ?? "none")),
    queryFn: async () =>
      (await QueriesService.readRun({ path: { run_id: id.value as string } })).data,
    enabled: computed(() => id.value !== null),
    refetchInterval: (query) =>
      LIVE.has(query.state.data?.status ?? "") ? 1000 : false,
  })
}

export function useCancelRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (runId: string) =>
      (await QueriesService.cancelRun({ path: { run_id: runId } })).data,
    onSuccess: (run) => queryClient.setQueryData(runKey(run.id), run),
  })
}

export function useResultPage(
  resultId: MaybeRefOrGetter<string | null>,
  request: MaybeRefOrGetter<SnapshotPageRequest>
) {
  const id = computed(() => toValue(resultId))
  const body = computed(() => toValue(request))
  return useQuery({
    queryKey: computed(() =>
      resultKey(id.value ?? "none", body.value.view, body.value.offset ?? 0, body.value.limit ?? 100)
    ),
    queryFn: async () =>
      (
        await QueriesService.readResultPage({
          path: { result_id: id.value as string },
          body: body.value,
        })
      ).data,
    enabled: computed(() => id.value !== null),
    // A snapshot does not change. Re-reading it would only cost a round trip.
    staleTime: Infinity,
    retry: false,
  })
}

export function useDownloadResult() {
  return useMutation({
    mutationFn: async (request: { resultId: string; body: SnapshotDownloadRequest }) => {
      const response = await QueriesService.downloadResult({
        path: { result_id: request.resultId },
        body: request.body,
        responseType: "blob",
      })
      return {
        blob: response.data as unknown as Blob,
        disposition: response.headers["content-disposition"] as string | undefined,
      }
    },
  })
}

/**
 * What this connection holds, for completion and for conservative marks.
 *
 * Kept for as long as the source says its catalog is worth keeping, and asked
 * again when the console names a relation it has not asked about yet — which
 * is what "progressive" means here (D65).
 */
export function useQueryMetadata(
  connectorId: MaybeRefOrGetter<string | null>,
  request: MaybeRefOrGetter<QueryMetadataRequest>
) {
  const id = computed(() => toValue(connectorId))
  const body = computed(() => toValue(request))
  return useQuery({
    queryKey: computed(
      () => ["queries", "metadata", id.value ?? "none", JSON.stringify(body.value)] as const
    ),
    queryFn: async () =>
      (
        await QueriesService.readMetadata({
          path: { connector_id: id.value as string },
          body: body.value,
        })
      ).data,
    enabled: computed(() => id.value !== null),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Plan one statement without running it (D65).
 *
 * A request of its own rather than a run: there is nothing to cancel and
 * nothing is captured, so there is no lifecycle to watch.
 */
/**
 * Whether writing is open on this connection, and until when (D66).
 *
 * Server state like everything else, and asked again after every unlock:
 * whether a person may change anything is not something a screen decides.
 */
export function useUnlockState(connectorId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(connectorId))
  return useQuery({
    queryKey: computed(() => ["queries", "unlock", id.value ?? "none"] as const),
    queryFn: async () =>
      (await QueriesService.readUnlock({ path: { connector_id: id.value as string } }))
        .data,
    enabled: computed(() => id.value !== null),
    retry: false,
  })
}

export function useOpenWrites() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (request: { connectorId: string; connectorName: string }) =>
      (
        await QueriesService.openWrites({
          path: { connector_id: request.connectorId },
          body: { connector_name: request.connectorName },
        })
      ).data,
    onSuccess: (state) =>
      queryClient.setQueryData(["queries", "unlock", state.connector_id], state),
  })
}

export function useCloseWrites() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (
        await QueriesService.closeWrites({ path: { connector_id: connectorId } })
      ).data,
    onSuccess: (state) =>
      queryClient.setQueryData(["queries", "unlock", state.connector_id], state),
  })
}

/**
 * One open transaction, re-read while it is open.
 *
 * The interval is what makes the countdown honest: the lease is the server's,
 * and a console that guessed at it would show a promise it cannot keep (D66).
 */
export function useTransaction(transactionId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(transactionId))
  return useQuery({
    queryKey: computed(() => ["queries", "transactions", id.value ?? "none"] as const),
    queryFn: async () =>
      (
        await QueriesService.readTransaction({
          path: { transaction_id: id.value as string },
        })
      ).data,
    enabled: computed(() => id.value !== null),
    refetchInterval: 5000,
    retry: false,
  })
}

export function useOpenTransaction() {
  return useMutation({
    mutationFn: async (body: TransactionStart) =>
      (await QueriesService.openTransaction({ body })).data,
  })
}

export function useEndTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (request: { transactionId: string; commit: boolean }) =>
      request.commit
        ? (
            await QueriesService.commitTransaction({
              path: { transaction_id: request.transactionId },
            })
          ).data
        : (
            await QueriesService.rollbackTransaction({
              path: { transaction_id: request.transactionId },
            })
          ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["queries", "runs"] })
      await queryClient.invalidateQueries({ queryKey: ["queries", "transactions"] })
    },
  })
}

export function useExplainQuery() {
  return useMutation({
    mutationFn: async (request: { connectorId: string; body: ExplainStart }) =>
      (
        await QueriesService.explainQuery({
          path: { connector_id: request.connectorId },
          body: request.body,
        })
      ).data,
  })
}

export function useFormatQuery() {
  return useMutation({
    mutationFn: async (request: { connectorId: string; text: string }) =>
      (
        await QueriesService.formatQuery({
          path: { connector_id: request.connectorId },
          body: { text: request.text },
        })
      ).data,
  })
}

export function useGenerateQuery() {
  return useMutation({
    mutationFn: async (request: {
      connectorId: string
      body: GenerateQueryRequest
    }) =>
      (
        await QueriesService.generateQuery({
          path: { connector_id: request.connectorId },
          body: request.body,
        })
      ).data,
  })
}

export function useRunHistory(
  documentId: MaybeRefOrGetter<string | null>,
  search: MaybeRefOrGetter<string>
) {
  const id = computed(() => toValue(documentId))
  const needle = computed(() => toValue(search))
  return useQuery({
    queryKey: computed(() => historyKey(id.value, needle.value)),
    queryFn: async () =>
      (
        await QueriesService.listRuns({
          query: {
            ...(id.value === null ? {} : { document_id: id.value }),
            search: needle.value,
          },
        })
      ).data,
  })
}

export function useRunText() {
  return useMutation({
    mutationFn: async (runId: string) =>
      (await QueriesService.readRunText({ path: { run_id: runId } })).data,
  })
}

export function useDeleteRuns() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: RunDeletion) =>
      (await QueriesService.deleteRuns({ body })).data,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["queries", "history"] }),
  })
}
