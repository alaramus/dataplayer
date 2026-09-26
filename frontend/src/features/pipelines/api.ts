import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { ConnectorsService, PipelinesService } from "@/client"
import type { Card, LinkEnd, LinkRun, PipelinePublic, PipelineSave, PipelineSummary } from "@/client"

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

export function runsKey(pipelineId: string) {
  return ["pipeline-runs", pipelineId] as const
}

export function useRuns(pipelineId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => runsKey(toValue(pipelineId))),
    queryFn: async () => (await PipelinesService.readRuns({ path: { pipeline_id: toValue(pipelineId) } })).data,
  })
}

/** One run kept in the list of runs, in place of the one before it. */
export function withRun(runs: readonly LinkRun[] | undefined, run: LinkRun): LinkRun[] {
  return [...(runs ?? []).filter((one) => one.link_id !== run.link_id), run]
}

export async function runLink(pipelineId: string, linkId: string) {
  return (await PipelinesService.runPipelineLink({ path: { pipeline_id: pipelineId, link_id: linkId } })).data
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
