import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { PipelinesService } from "@/client"
import { jobsKey } from "@/features/activity/api"
import type {
  Card, LinkEnd, PipelinePublic, PipelineRunPublic, PipelineSave, PipelineSummary, ScheduleSettings,
} from "@/client"

import { isRunning } from "./links"
import { checkedRowsKey } from "./model"

/**
 * Pipelines are server state (D6, D175). The draft of the one on the canvas is
 * the only thing held on the screen, and it is saved back whole.
 */
export const pipelinesKey = ["pipelines"] as const

export function pipelineKey(id: string) {
  return ["pipelines", id] as const
}

export function usePipelines() {
  return useQuery({
    queryKey: pipelinesKey,
    queryFn: async () => (await PipelinesService.readPipelines()).data,
  })
}

export function usePipeline(id: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => pipelineKey(toValue(id))),
    queryFn: async () => (await PipelinesService.readPipeline({ path: { pipeline_id: toValue(id) } })).data,
    retry: false,
  })
}

function listed(queryClient: ReturnType<typeof useQueryClient>, pipeline: PipelinePublic) {
  queryClient.setQueryData(pipelineKey(pipeline.id), pipeline)
  const entry: PipelineSummary = { id: pipeline.id, name: pipeline.name, updated_at: pipeline.updated_at }
  queryClient.setQueryData<PipelineSummary[]>(pipelinesKey, (list) => {
    const rest = (list ?? []).filter((one) => one.id !== pipeline.id)
    return [...rest, entry].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }))
  })
}

export function useCreatePipeline() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => (await PipelinesService.createPipeline({ body: { name } })).data,
    onSuccess: (pipeline) => {
      listed(queryClient, pipeline)
    },
  })
}

export function useSavePipeline() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: { id: string; body: PipelineSave }) =>
      (await PipelinesService.savePipeline({ path: { pipeline_id: input.id }, body: input.body })).data,
    onSuccess: (pipeline) => {
      listed(queryClient, pipeline)
    },
  })
}

export function useDeletePipeline() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await PipelinesService.deletePipeline({ path: { pipeline_id: id } })
      return id
    },
    onSuccess: (id) => {
      queryClient.removeQueries({ queryKey: pipelineKey(id) })
      queryClient.setQueryData<PipelineSummary[]>(pipelinesKey, (list) =>
        (list ?? []).filter((one) => one.id !== id)
      )
      // Its finished runs went with it, from the footer's activity too (D180).
      void queryClient.invalidateQueries({ queryKey: jobsKey })
    },
  })
}

/**
 * Whether a card's connection answers and which of its rows are gone.
 *
 * Asked of the card as the server keeps it, so it is keyed by the rows that
 * were saved: a card changed on the screen is asked again once it is stored.
 */
export function cardStateKey(pipelineId: string, card: Card) {
  return ["pipeline-card-state", pipelineId, card.id, checkedRowsKey(card)] as const
}

export async function readCardState(pipelineId: string, cardId: string) {
  return (await PipelinesService.readCardState({ path: { pipeline_id: pipelineId, card_id: cardId } })).data
}

/** The pipeline's last run (D177): its job, as the server reads it now. */
export function lastRunKey(pipelineId: string) {
  return ["pipeline-run", pipelineId] as const
}

export function useLastRun(pipelineId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => lastRunKey(toValue(pipelineId))),
    queryFn: async () =>
      (await PipelinesService.readLastRun({ path: { pipeline_id: toValue(pipelineId) } })).data.run ?? null,
    // Each step's end arrives by the socket; this is for a socket that missed it.
    refetchInterval: (query) => (isRunning(query.state.data) ? 3000 : false),
  })
}

/** The pipeline's runs and its schedule's skips and misses, newest first (D180). */
export function historyKey(pipelineId: string) {
  return ["pipeline-history", pipelineId] as const
}

export function useHistory(pipelineId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => historyKey(toValue(pipelineId))),
    queryFn: async () =>
      (await PipelinesService.readHistory({ path: { pipeline_id: toValue(pipelineId) } })).data.rows,
  })
}

/**
 * An older run pressed in the history, or none while the last is shown. Only
 * the last can still be going (D177), so what this reads has ended.
 */
export function usePastRun(pipelineId: MaybeRefOrGetter<string>, jobId: MaybeRefOrGetter<string | null>) {
  return useQuery({
    queryKey: computed(() => ["pipeline-past-run", toValue(pipelineId), toValue(jobId)] as const),
    queryFn: async () =>
      (await PipelinesService.readRun({
        path: { pipeline_id: toValue(pipelineId), job_id: toValue(jobId) ?? "" },
      })).data,
    enabled: computed(() => toValue(jobId) !== null),
    retry: false,
  })
}

/** Every link of the pipeline as saved, one after another, as one job. */
export async function runPipeline(pipelineId: string): Promise<PipelineRunPublic> {
  return (await PipelinesService.runPipeline({ path: { pipeline_id: pipelineId } })).data
}

/** The pipeline's schedule and when it comes next (D179). */
export function scheduleKey(pipelineId: string) {
  return ["pipeline-schedule", pipelineId] as const
}

export function useSchedule(pipelineId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => scheduleKey(toValue(pipelineId))),
    queryFn: async () => (await PipelinesService.readSchedule({ path: { pipeline_id: toValue(pipelineId) } })).data,
  })
}

export function useSaveSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: { pipelineId: string; settings: ScheduleSettings }) =>
      (await PipelinesService.setSchedule({ path: { pipeline_id: input.pipelineId }, body: input.settings })).data,
    onSuccess: (schedule, input) => {
      queryClient.setQueryData(scheduleKey(input.pipelineId), schedule)
    },
  })
}

/** The links a refused run named as lacking a choice, first in run order. */
export function lackingLinks(cause: unknown): string[] {
  if (!(cause instanceof AxiosError)) return []
  const detail: unknown = cause.response?.data?.detail
  if (detail === null || typeof detail !== "object" || !("link_ids" in detail)) return []
  const ids: unknown = detail.link_ids
  return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : []
}

export async function readHint(pipelineId: string, cardId: string | null) {
  return (await PipelinesService.readHint({ path: { pipeline_id: pipelineId }, body: { card_id: cardId } })).data
}

/** One end of a link and the connection its card is on. */
export interface LinkSide {
  connectorId: string
  end: LinkEnd
}

/**
 * Keyed by both ends and by the links making what either end is (D178): a
 * choice changed along a chain changes the answer.
 */
export function linkOffersKey(pipelineId: string, from: LinkSide, to: LinkSide, chain: string) {
  const at = (side: LinkSide) => [side.connectorId, side.end.card_id, side.end.node_id ?? null, side.end.made_by ?? null]
  return ["link-offers", pipelineId, ...at(from), ...at(to), chain] as const
}

/**
 * What can go from one row into another, asked of the pipeline as kept: the
 * pair window's question for two ticked rows (D167), and for what a link
 * makes, the same question of it as it will be made (D178).
 */
export async function readLinkOffers(pipelineId: string, from: LinkSide, to: LinkSide) {
  return (await PipelinesService.readLinkOffers({
    path: { pipeline_id: pipelineId },
    body: { source: from.end, target: to.end },
  })).data.offers
}
