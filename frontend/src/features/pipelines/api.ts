import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { PipelinesService } from "@/client"
import type { Card, PipelinePublic, PipelineSave, PipelineSummary } from "@/client"

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
