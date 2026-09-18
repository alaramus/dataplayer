import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { AiService } from "@/client"
import type { AgentSettingsUpdate, ConversationUpdate, ScreenContext } from "@/client"

export const aiModelsKey = ["ai", "models"] as const
export const aiSettingsKey = ["ai", "settings"] as const
export const aiConversationsKey = ["ai", "conversations"] as const
export const aiArchivedConversationsKey = ["ai", "archived-conversations"] as const
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

/** What the history does not show. Only the settings ask for it. */
export function useArchivedAiConversations() {
  return useQuery({
    queryKey: aiArchivedConversationsKey,
    queryFn: async () => (
      await AiService.readConversations({ query: { archived: true } })
    ).data,
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
  // Both lists, always: archiving moves a row from one to the other, and a
  // stale archive is how a restored chat appears in two places at once.
  return async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: aiConversationsKey })
    await queryClient.invalidateQueries({ queryKey: aiArchivedConversationsKey })
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

export function useUpdateAiConversation() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, ...change }: { id: string } & ConversationUpdate) => (
      await AiService.updateConversation({ path: { conversation_id: id }, body: change })
    ).data,
    onSuccess: (changed) => invalidate(changed.id),
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

export function useDeleteArchivedAiConversations() {
  const queryClient = useQueryClient()
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async () => { await AiService.deleteArchivedConversations() },
    onSuccess: async () => {
      // Every conversation page cached under a now deleted id goes with them.
      queryClient.removeQueries({ queryKey: aiConversationsKey })
      await invalidate()
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

export function useAnswerAiRun() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, conversationId, answer }: { id: string; conversationId: string; answer: string }) => {
      const run = (await AiService.answerRun({ path: { run_id: id }, body: { answer } })).data
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

/**
 * Whether a key works, before anybody decides to keep it.
 *
 * The key typed into the form is sent for the check and stored by nothing; an
 * empty one asks about the key already saved for that provider.
 */
export async function checkAiKey(
  provider: "openai" | "anthropic" | "deepseek" | "gemini",
  key: string | null = null
) {
  return (await AiService.checkKey({ path: { provider }, body: { key } })).data
}
