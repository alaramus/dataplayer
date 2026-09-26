import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { ConnectorsService, PipelinesService } from "@/client"
import type { Card, LinkEnd, PipelinePublic, PipelineRunPublic, PipelineSave, PipelineSummary } from "@/client"

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

/** Every link of the pipeline as saved, one after another, as one job. */
export async function runPipeline(pipelineId: string): Promise<PipelineRunPublic> {
  return (await PipelinesService.runPipeline({ path: { pipeline_id: pipelineId } })).data
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

/** One end of a link as a connection and a node, which is what the offers are asked of. */
export interface LinkSide {
  connectorId: string
  end: LinkEnd
}

export function linkOffersKey(from: LinkSide, to: LinkSide) {
  return ["link-offers", from.connectorId, from.end.node_id ?? null, to.connectorId, to.end.node_id ?? null] as const
}

/**
 * What can go from one row into another: the pair window's question with
 * one tick on each side, the target standing for the place as well (D167).
 */
export async function readLinkOffers(from: LinkSide, to: LinkSide) {
  const target = to.end.node_id ?? null
  return (await ConnectorsService.pairOffers({
    body: {
      source: { connector_id: from.connectorId, place: null, ticked: from.end.node_id == null ? [] : [from.end.node_id] },
      destination: { connector_id: to.connectorId, place: target, ticked: target === null ? [] : [target] },
    },
  })).data.offers
}
