import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, onScopeDispose } from "vue"
import type { MaybeRefOrGetter } from "vue"
import { toValue } from "vue"

import { MetricsService } from "@/client"
import type {
  DashboardGrantWrite,
  DashboardPublic,
  DashboardSave,
  HistoryAnswer,
  ReportingUpdate,
  StoreStatus,
} from "@/client"
import { isJobEvent, JOBS_TOPIC } from "@/features/services/jobs"
import { realtime } from "@/shared/realtime/client"

import { windowOf } from "./dashboardModel"
import type { ProcessLimit, ProcessSort } from "./dashboardModel"
import { isLivePoints, LIVE_TOPIC, mergeLive } from "./livePoints"

/**
 * Metrics are server state, so they live in vue-query (D6). The draft of the
 * dashboard being edited is the one thing held on the screen, and it is saved
 * back whole.
 */
export const storeStatusKey = ["metrics-store"] as const
export const agentsKey = ["metrics-agents"] as const
export const metricsCatalogKey = ["metrics-catalog"] as const
export const dashboardsKey = ["metrics-dashboards"] as const
const HISTORY_KEY = "metrics-history"

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

export const hostsKey = ["metrics-hosts"] as const

/** The hosts the person's agents report, and what each one is. */
export function useHosts(enabled: MaybeRefOrGetter<boolean> = true) {
  return useQuery({
    queryKey: hostsKey,
    queryFn: async () => (await MetricsService.readHosts()).data,
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
      await queryClient.invalidateQueries({ queryKey: hostsKey })
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
  maxPoints: MaybeRefOrGetter<number> = 600,
  /** The dashboard the series are drawn on, which may be how they are readable (D129). */
  dashboardId: MaybeRefOrGetter<string | null> = null
) {
  return useQuery({
    queryKey: computed(() => [
      HISTORY_KEY,
      [...toValue(seriesIds)].sort((a, b) => a - b).join(","),
      toValue(rangeSeconds),
      toValue(maxPoints),
      toValue(dashboardId),
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
            dashboard_id: toValue(dashboardId),
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

/**
 * Lay the points the socket pushes onto every history already read, for as
 * long as the caller lives. Several callers are harmless: merging is
 * idempotent.
 */
export function useLivePoints() {
  const queryClient = useQueryClient()
  const stop = realtime().subscribe(LIVE_TOPIC, (payload) => {
    if (!isLivePoints(payload)) return
    const now = Math.floor(Date.now() / 1000)
    for (const [key, answer] of queryClient.getQueriesData<HistoryAnswer>({ queryKey: [HISTORY_KEY] })) {
      if (answer === undefined) continue
      const range = Number(key[2])
      const merged = mergeLive(answer, payload, range, now)
      if (merged !== null) queryClient.setQueryData(key, merged)
    }
  })
  onScopeDispose(stop)
}

export function useProcesses(
  agentId: MaybeRefOrGetter<string>,
  host: MaybeRefOrGetter<string>,
  sort: MaybeRefOrGetter<ProcessSort>,
  limit: MaybeRefOrGetter<ProcessLimit>,
  refreshSeconds: MaybeRefOrGetter<number>,
  dashboardId: MaybeRefOrGetter<string | null> = null
) {
  return useQuery({
    queryKey: computed(() => [
      "metrics-processes", toValue(agentId), toValue(host), toValue(sort), toValue(limit), toValue(dashboardId),
    ] as const),
    queryFn: async ({ signal }) =>
      (
        await MetricsService.readProcesses({
          query: {
            agent_id: toValue(agentId),
            host: toValue(host),
            sort: toValue(sort),
            limit: toValue(limit),
            dashboard_id: toValue(dashboardId),
          },
          signal,
        })
      ).data,
    placeholderData: keepPreviousData,
    // A table arrives at the agent's pace, so without an interval of the
    // dashboard's it is still read every half minute.
    refetchInterval: computed(() => {
      const seconds = toValue(refreshSeconds)
      return (seconds > 0 ? seconds : 30) * 1000
    }),
  })
}

/** What a ready-made layout is asked for: one host of an agent, or one connection. */
export type PresetTarget =
  | { kind: "host"; agentId: string; host: string; label: string }
  | { kind: "connector"; connectorId: string; label: string }

export function usePresets(target: MaybeRefOrGetter<PresetTarget | null>) {
  return useQuery({
    queryKey: computed(() => {
      const chosen = toValue(target)
      if (chosen === null) return ["metrics-presets", "none"] as const
      return chosen.kind === "host"
        ? (["metrics-presets", chosen.agentId, chosen.host] as const)
        : (["metrics-presets", chosen.connectorId] as const)
    }),
    queryFn: async () => {
      const chosen = toValue(target)
      if (chosen === null) return []
      const query = chosen.kind === "host"
        ? { agent_id: chosen.agentId, host: chosen.host }
        : { connector_id: chosen.connectorId }
      return (await MetricsService.readPresets({ query })).data
    },
    enabled: computed(() => toValue(target) !== null),
  })
}

export const reportingKey = ["metrics-reporting"] as const

export function useReporting(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: reportingKey,
    queryFn: async () => (await MetricsService.readReporting()).data,
    enabled: computed(() => toValue(enabled)),
    refetchInterval: 30_000,
  })
}

export function useUpdateReporting() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: { connectorId: string; body: ReportingUpdate }) =>
      (await MetricsService.updateReporting({ path: { connector_id: input.connectorId }, body: input.body })).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: reportingKey })
      await queryClient.invalidateQueries({ queryKey: metricsCatalogKey })
    },
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

/** Where the store is and what it holds; a superuser's, before removing it. */
export function useStoreUsage(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: ["metrics-store-usage"] as const,
    queryFn: async () => (await MetricsService.readStoreUsage()).data,
    enabled: computed(() => toValue(enabled)),
  })
}

export function useRemoveStore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => (await MetricsService.removeStore()).data,
    // Every answer about metrics came from the store that is gone.
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        predicate: (query) => String(query.queryKey[0]).startsWith("metrics-"),
      })
    },
  })
}

/**
 * Hosts of the person's agents that keep restarting (D130). Read by the
 * activity sheet on every screen, so slowly: restarts that need a person are
 * counted over a quarter of an hour.
 */
export function useRestarts() {
  return useQuery({
    queryKey: ["metrics-restarts"] as const,
    queryFn: async () => (await MetricsService.readRestarts()).data,
    refetchInterval: 60_000,
  })
}

/** The names of what is on one dashboard, as the caller may read it through the dashboard. */
export function useDashboardCatalog(dashboardId: MaybeRefOrGetter<string | null>) {
  return useQuery({
    queryKey: computed(() => ["metrics-dashboard-catalog", toValue(dashboardId)] as const),
    queryFn: async () =>
      (await MetricsService.readDashboardCatalog({ path: { dashboard_id: toValue(dashboardId) as string } })).data,
    enabled: computed(() => toValue(dashboardId) !== null),
    refetchInterval: 60_000,
  })
}

const dashboardGrantsKey = (dashboardId: string) => ["metrics-dashboard-grants", dashboardId] as const

/** Who else may see a dashboard. The owner's list; anybody else is refused it. */
export function useDashboardGrants(dashboardId: MaybeRefOrGetter<string | null>) {
  return useQuery({
    queryKey: computed(() => dashboardGrantsKey(toValue(dashboardId) ?? "none")),
    queryFn: async () =>
      (await MetricsService.readDashboardGrants({ path: { dashboard_id: toValue(dashboardId) as string } })).data,
    enabled: computed(() => toValue(dashboardId) !== null),
  })
}

export function useWriteDashboardGrant(dashboardId: MaybeRefOrGetter<string>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: DashboardGrantWrite) =>
      (await MetricsService.writeDashboardGrant({ path: { dashboard_id: toValue(dashboardId) }, body })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dashboardGrantsKey(toValue(dashboardId)) }),
  })
}

export function useRevokeDashboardGrant(dashboardId: MaybeRefOrGetter<string>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (userId: string) =>
      (await MetricsService.revokeDashboardGrant({ path: { dashboard_id: toValue(dashboardId), user_id: userId } })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: dashboardGrantsKey(toValue(dashboardId)) }),
  })
}
