import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { AiService } from "@/client"
import type { AgentSettingsUpdate, ScreenContext } from "@/client"

export const aiModelsKey = ["ai", "models"] as const
export const aiSettingsKey = ["ai", "settings"] as const
export const aiConversationsKey = ["ai", "conversations"] as const
export const aiConversationKey = (id: string) => ["ai", "conversations", id] as const

export function useAiModels() {
  return useQuery({
    queryKey: aiModelsKey,
    queryFn: async () => (await AiService.readModels()).data,
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useAiSettings() {
  return useQuery({
    queryKey: aiSettingsKey,
    queryFn: async () => (await AiService.readSettings()).data,
  })
}

export function useAiConversations() {
  return useQuery({
    queryKey: aiConversationsKey,
    queryFn: async () => (await AiService.readConversations()).data,
  })
}

export function useAiConversation(id: MaybeRefOrGetter<string | null>) {
  const current = computed(() => toValue(id))
  return useQuery({
    queryKey: computed(() => aiConversationKey(current.value ?? "none")),
    queryFn: async () => (
      await AiService.readConversation({ path: { conversation_id: current.value as string } })
    ).data,
    enabled: computed(() => current.value !== null),
    refetchOnWindowFocus: false,
  })
}

function useConversationInvalidation() {
  const queryClient = useQueryClient()
  return async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: aiConversationsKey })
    if (id !== undefined) await queryClient.invalidateQueries({ queryKey: aiConversationKey(id) })
  }
}

export function useCreateAiConversation() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async () => (await AiService.createConversation()).data,
    onSuccess: (created) => invalidate(created.id),
  })
}

export function useRenameAiConversation() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) => (
      await AiService.renameConversation({ path: { conversation_id: id }, body: { title } })
    ).data,
    onSuccess: (renamed) => invalidate(renamed.id),
  })
}

export function useDeleteAiConversation() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async (id: string) => {
      await AiService.deleteConversation({ path: { conversation_id: id } })
      return id
    },
    onSuccess: (id) => invalidate(id),
  })
}

export function useDeleteAllAiConversations() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => { await AiService.deleteAllConversations() },
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ["ai", "conversations"] })
      await queryClient.invalidateQueries({ queryKey: aiConversationsKey })
    },
  })
}

export function useSendAiMessage() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, text, contexts }: { id: string; text: string; contexts: ScreenContext[] }) => (
      await AiService.sendMessage({ path: { conversation_id: id }, body: { text, contexts } })
    ).data,
    onSuccess: (run) => invalidate(run.conversation_id),
  })
}

export function useCancelAiRun() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, conversationId }: { id: string; conversationId: string }) => {
      const run = (await AiService.cancelRun({ path: { run_id: id } })).data
      return { run, conversationId }
    },
    onSuccess: ({ conversationId }) => invalidate(conversationId),
  })
}

export function useUpdateAiSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: AgentSettingsUpdate) => (await AiService.updateSettings({ body })).data,
    onSuccess: (settings) => queryClient.setQueryData(aiSettingsKey, settings),
  })
}

export function useWriteAiKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ provider, key }: { provider: "openai" | "anthropic" | "deepseek" | "gemini"; key: string }) => (
      await AiService.writeKey({ path: { provider }, body: { key } })
    ).data,
    onSuccess: (settings) => {
      queryClient.setQueryData(aiSettingsKey, settings)
      void queryClient.invalidateQueries({ queryKey: aiModelsKey })
    },
  })
}

export function useRemoveAiKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (provider: "openai" | "anthropic" | "deepseek" | "gemini") => (
      await AiService.removeKey({ path: { provider } })
    ).data,
    onSuccess: (settings) => {
      queryClient.setQueryData(aiSettingsKey, settings)
      void queryClient.invalidateQueries({ queryKey: aiModelsKey })
    },
  })
}

export async function checkAiKey(provider: "openai" | "anthropic" | "deepseek" | "gemini") {
  return (await AiService.checkKey({ path: { provider } })).data
}
