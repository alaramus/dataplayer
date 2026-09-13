import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, onScopeDispose } from "vue"
import type { MaybeRefOrGetter } from "vue"
import { toValue } from "vue"

import { MetricsService } from "@/client"
import type { DashboardPublic, DashboardSave, StoreStatus } from "@/client"
import { isJobEvent, JOBS_TOPIC } from "@/features/services/jobs"
import { realtime } from "@/shared/realtime/client"

import { windowOf } from "./dashboardModel"

/**
 * Metrics are server state, so they live in vue-query (D6). The draft of the
 * dashboard being edited is the one thing held on the screen, and it is saved
 * back whole.
 */
export const storeStatusKey = ["metrics-store"] as const
export const agentsKey = ["metrics-agents"] as const
export const metricsCatalogKey = ["metrics-catalog"] as const
export const dashboardsKey = ["metrics-dashboards"] as const

export function useStoreStatus() {
  return useQuery({
    queryKey: storeStatusKey,
    queryFn: async () => (await MetricsService.readStoreStatus()).data,
    // While it starts, the job's own events say when to look again; this is
    // the fallback for an event that never arrives.
    refetchInterval: (query) => (query.state.data?.state === "starting" ? 3000 : false),
  })
}

/** Re-read the store's status whenever its starting job moves. */
export function useStoreJobEvents() {
  const queryClient = useQueryClient()
  const stop = realtime().subscribe(JOBS_TOPIC, (payload) => {
    if (!isJobEvent(payload) || !payload.kind.startsWith("metrics.")) return
    void queryClient.invalidateQueries({ queryKey: storeStatusKey })
  })
  onScopeDispose(stop)
}

function settles(status: StoreStatus, queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.setQueryData(storeStatusKey, status)
}

export function useStartStore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => (await MetricsService.startStore()).data,
    onSuccess: (status) => {
      settles(status, queryClient)
    },
  })
}

export function useConnectStore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (options: Record<string, unknown>) =>
      (await MetricsService.connectStore({ body: { options } })).data,
    onSuccess: (status) => {
      settles(status, queryClient)
    },
  })
}

export function useAgents(enabled: MaybeRefOrGetter<boolean> = true) {
  return useQuery({
    queryKey: agentsKey,
    queryFn: async () => (await MetricsService.readAgents()).data,
    enabled: computed(() => toValue(enabled)),
    refetchInterval: 30_000,
  })
}

function useAgentMutation<Input, Output>(run: (input: Input) => Promise<Output>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: agentsKey })
      await queryClient.invalidateQueries({ queryKey: metricsCatalogKey })
    },
  })
}

export function useCreateAgent() {
  return useAgentMutation(async (name: string) => (await MetricsService.createAgent({ body: { name } })).data)
}

export function useRenameAgent() {
  return useAgentMutation(async (input: { id: string; name: string }) =>
    (await MetricsService.renameAgent({ path: { agent_id: input.id }, body: { name: input.name } })).data
  )
}

export function useDeleteAgent() {
  return useAgentMutation(async (id: string) => (await MetricsService.deleteAgent({ path: { agent_id: id } })).data)
}

export function usePurgeAgent() {
  return useAgentMutation(async (id: string) => (await MetricsService.purgeAgent({ path: { agent_id: id } })).data)
}

export function useRotateAgentKey() {
  return useAgentMutation(async (id: string) => (await MetricsService.rotateAgentKey({ path: { agent_id: id } })).data)
}

export async function readAgentKey(id: string) {
  return (await MetricsService.readAgentKey({ path: { agent_id: id } })).data
}

export function useMetricsCatalog(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: metricsCatalogKey,
    queryFn: async () => (await MetricsService.readCatalog()).data,
    enabled: computed(() => toValue(enabled)),
    // New series appear as agents report; a minute is soon enough for a tree.
    refetchInterval: 60_000,
  })
}

/**
 * The points of one widget over the dashboard's range, re-read on its interval.
 *
 * Keyed by the series and the range, not by the moment: the window slides at
 * every fetch, and a key carrying the moment would be a new query each time.
 */
export function useHistory(
  seriesIds: MaybeRefOrGetter<readonly number[]>,
  rangeSeconds: MaybeRefOrGetter<number>,
  refreshSeconds: MaybeRefOrGetter<number>,
  maxPoints: MaybeRefOrGetter<number> = 600
) {
  return useQuery({
    queryKey: computed(() => [
      "metrics-history",
      [...toValue(seriesIds)].sort((a, b) => a - b).join(","),
      toValue(rangeSeconds),
      toValue(maxPoints),
    ] as const),
    queryFn: async ({ signal }) => {
      const { start, end } = windowOf(toValue(rangeSeconds), Date.now())
      return (
        await MetricsService.readHistory({
          body: {
            series_ids: [...toValue(seriesIds)],
            start,
            end,
            max_points: toValue(maxPoints),
          },
          signal,
        })
      ).data
    },
    enabled: computed(() => toValue(seriesIds).length > 0),
    placeholderData: keepPreviousData,
    refetchInterval: computed(() => {
      const seconds = toValue(refreshSeconds)
      return seconds > 0 ? seconds * 1000 : false
    }),
  })
}

export function useDashboards(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: dashboardsKey,
    queryFn: async () => (await MetricsService.readDashboards()).data,
    enabled: computed(() => toValue(enabled)),
  })
}

function replaceInList(
  queryClient: ReturnType<typeof useQueryClient>,
  dashboard: DashboardPublic
) {
  queryClient.setQueryData<DashboardPublic[]>(dashboardsKey, (list) => {
    if (list === undefined) return [dashboard]
    const found = list.some((one) => one.id === dashboard.id)
    return found ? list.map((one) => (one.id === dashboard.id ? dashboard : one)) : [...list, dashboard]
  })
}

export function useCreateDashboard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => (await MetricsService.createDashboard({ body: { name } })).data,
    onSuccess: (dashboard) => {
      replaceInList(queryClient, dashboard)
    },
  })
}

export function useSaveDashboard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: { id: string; body: DashboardSave }) =>
      (await MetricsService.saveDashboard({ path: { dashboard_id: input.id }, body: input.body })).data,
    onSuccess: (dashboard) => {
      replaceInList(queryClient, dashboard)
    },
  })
}

export function useDeleteDashboard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await MetricsService.deleteDashboard({ path: { dashboard_id: id } })
      return id
    },
    onSuccess: (id) => {
      queryClient.setQueryData<DashboardPublic[]>(dashboardsKey, (list) =>
        (list ?? []).filter((one) => one.id !== id)
      )
    },
  })
}
