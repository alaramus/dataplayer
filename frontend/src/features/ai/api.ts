import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { AiService } from "@/client"
import type { AgentSettingsUpdate, ConversationUpdate, QuickChatSummary, QuickChatUpdate, ScreenContext } from "@/client"

import type { Provider } from "./modelOptions"
import { forgetQuickChat } from "./quickChatLauncher"

export const aiModelsKey = ["ai", "models"] as const
export const aiSettingsKey = ["ai", "settings"] as const
export const aiConversationsKey = ["ai", "conversations"] as const
export const aiArchivedConversationsKey = ["ai", "archived-conversations"] as const
export const aiConversationKey = (id: string) => ["ai", "conversations", id] as const
export const aiProjectsKey = ["ai", "projects"] as const
export const quickChatsKey = ["ai", "quick-chats"] as const
export const quickArchivedChatsKey = ["ai", "quick-chats-archived"] as const

export function useQuickChats() {
  return useQuery({
    queryKey: quickChatsKey,
    queryFn: async () => (await AiService.listQuickChats()).data,
  })
}

export function useArchivedQuickChats() {
  return useQuery({
    queryKey: quickArchivedChatsKey,
    queryFn: async () => (await AiService.listQuickChats({ query: { archived: true } })).data,
  })
}

function useQuickChatInvalidation() {
  const queryClient = useQueryClient()
  return async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: quickChatsKey })
    await queryClient.invalidateQueries({ queryKey: quickArchivedChatsKey })
    if (id) await queryClient.invalidateQueries({ queryKey: ["ai", "quick-chat", id] })
  }
}

export function useUpdateQuickChat() {
  const invalidate = useQuickChatInvalidation()
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: string } & QuickChatUpdate) => (
      await AiService.updateQuickChat({ path: { chat_id: id }, body })
    ).data,
    onSuccess: (chat) => invalidate(chat.id),
  })
}

export function useDeleteQuickChat() {
  const queryClient = useQueryClient()
  const invalidate = useQuickChatInvalidation()
  return useMutation({
    mutationFn: async (id: string) => {
      await AiService.deleteQuickChat({ path: { chat_id: id } })
      return id
    },
    onSuccess: async (id) => {
      forgetQuickChat(id)
      queryClient.removeQueries({ queryKey: ["ai", "quick-chat", id] })
      await invalidate()
    },
  })
}

export function useDeleteArchivedQuickChats() {
  const queryClient = useQueryClient()
  const invalidate = useQuickChatInvalidation()
  return useMutation({
    mutationFn: async () => { await AiService.deleteArchivedQuickChats() },
    onSuccess: async () => {
      for (const chat of queryClient.getQueryData<QuickChatSummary[]>(quickArchivedChatsKey) ?? []) {
        forgetQuickChat(chat.id)
      }
      queryClient.removeQueries({ queryKey: ["ai", "quick-chat"] })
      await invalidate()
    },
  })
}

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
  const queryClient = useQueryClient()
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, ...change }: { id: string } & ConversationUpdate) => (
      await AiService.updateConversation({ path: { conversation_id: id }, body: change })
    ).data,
    onSuccess: async (changed, change) => {
      // The server keeps a chat's model as the person's choice as well (D140).
      if (change.model_key) await queryClient.invalidateQueries({ queryKey: aiSettingsKey })
      await invalidate(changed.id)
    },
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

export function useAiProjects() {
  return useQuery({
    queryKey: aiProjectsKey,
    queryFn: async () => (await AiService.readProjects()).data,
  })
}

export function useCreateAiProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => (
      await AiService.createProject({ body: { name } })
    ).data,
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: aiProjectsKey }) },
  })
}

export function useRenameAiProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => (
      await AiService.renameProject({ path: { project_id: id }, body: { name } })
    ).data,
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: aiProjectsKey }) },
  })
}

export function useDeleteAiProject() {
  const queryClient = useQueryClient()
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, chats }: { id: string; chats: "keep" | "archive" }) => {
      await AiService.deleteProject({ path: { project_id: id }, query: { chats } })
      return id
    },
    // The chats it held are still there, in no folder: in the history or the archive.
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: aiProjectsKey })
      await invalidate()
      await queryClient.invalidateQueries({ queryKey: quickChatsKey })
      await queryClient.invalidateQueries({ queryKey: quickArchivedChatsKey })
    },
  })
}

export function useSendAiMessage() {
  const invalidate = useConversationInvalidation()
  return useMutation({
    mutationFn: async ({ id, text, contexts, files }: {
      id: string
      text: string
      contexts: ScreenContext[]
      files: File[]
    }) => (
      // A form, for the files; the tabs are a JSON field of it (D142).
      await AiService.sendMessage({
        path: { conversation_id: id },
        body: { text, contexts: JSON.stringify(contexts), files },
      })
    ).data,
    onSuccess: (run) => invalidate(run.conversation_id),
  })
}

/** A file sent with a message, as the bytes it was sent as. */
export async function fetchAiAttachment(conversationId: string, attachmentId: string): Promise<Blob> {
  return (
    await AiService.readAttachment({
      path: { conversation_id: conversationId, attachment_id: attachmentId },
      responseType: "blob",
    })
  ).data as Blob
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
    mutationFn: async ({ provider, key }: { provider: Provider; key: string }) => (
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
    mutationFn: async (provider: Provider) => (
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
  provider: Provider,
  key: string | null = null
) {
  return (await AiService.checkKey({ path: { provider }, body: { key } })).data
}
