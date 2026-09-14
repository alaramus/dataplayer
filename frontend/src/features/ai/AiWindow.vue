<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onScopeDispose, ref, watch } from "vue"

import type { AgentRunPublic, AgentStepPublic, ConversationPublic, ConversationsPublic } from "@/client"
import { AppButton, AppIconButton, AppInput, AppSpinner, useConfirm, useToast } from "@/shared/ui"
import { realtime } from "@/shared/realtime/client"
import { messageOf } from "@/shared/api/errors"

import AiConversation from "./AiConversation.vue"
import AiSettings from "./AiSettings.vue"
import { aiConversationKey, aiConversationsKey, useAiConversations, useCreateAiConversation, useDeleteAiConversation, useDeleteAllAiConversations, useRenameAiConversation } from "./api"
import { rememberAiConversation, rememberedAiConversation } from "./state"

type AiEvent =
  | { kind: "run"; conversation_id: string; run_id: string; status: AgentRunPublic["status"]; error?: string | null }
  | { kind: "step"; conversation_id: string; run_id: string; step: AgentStepPublic }
  | { kind: "answer"; conversation_id: string; run_id: string; text: string }
  | { kind: "reasoning"; conversation_id: string; run_id: string; ordinal: number; text: string }
  | { kind: "title"; conversation_id: string; title: string }

const list = useAiConversations()
const createConversation = useCreateAiConversation()
const renameConversation = useRenameAiConversation()
const deleteConversation = useDeleteAiConversation()
const deleteAll = useDeleteAllAiConversations()
const queryClient = useQueryClient()
const confirm = useConfirm()
const toast = useToast()
const selected = ref<string | null>(rememberedAiConversation())
const settingsShown = ref(false)
const collapsed = ref(false)
const renaming = ref<string | null>(null)
const titleDraft = ref("")

const conversations = computed(() => list.data.value?.data ?? [])

watch(conversations, (rows) => {
  if (selected.value !== null && rows.some((row) => row.id === selected.value)) return
  selected.value = rows[0]?.id ?? null
}, { immediate: true })
watch(selected, (id) => rememberAiConversation(id))

async function makeConversation() {
  try { const created = await createConversation.mutateAsync(); selected.value = created.id; settingsShown.value = false }
  catch (cause) { toast.error(messageOf(cause, "A new chat could not be created")) }
}
function select(id: string) { selected.value = id; settingsShown.value = false }
function beginRename(id: string, title: string) { renaming.value = id; titleDraft.value = title }
async function finishRename() {
  const id = renaming.value
  const title = titleDraft.value.trim()
  if (!id || !title) return
  try { await renameConversation.mutateAsync({ id, title }); renaming.value = null }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be renamed")) }
}
async function remove(id: string, title: string) {
  if (!(await confirm({ title: "Delete chat?", message: `“${title}” will be permanently deleted.`, confirmLabel: "Delete", danger: true }))) return
  try { await deleteConversation.mutateAsync(id); if (selected.value === id) selected.value = null }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be deleted")) }
}
async function removeAll() {
  if (!(await confirm({ title: "Delete all chats?", message: "Every conversation will be permanently deleted.", confirmLabel: "Delete all", danger: true }))) return
  try { await deleteAll.mutateAsync(); selected.value = null }
  catch (cause) { toast.error(messageOf(cause, "The chats could not be deleted")) }
}

function eventOf(payload: unknown): AiEvent | null {
  if (typeof payload !== "object" || payload === null || !("kind" in payload) || !("conversation_id" in payload)) return null
  return payload as AiEvent
}
function updateRun(conversationId: string, runId: string, change: (run: AgentRunPublic) => AgentRunPublic) {
  queryClient.setQueryData<ConversationPublic>(aiConversationKey(conversationId), (current) => current === undefined ? current : {
    ...current, runs: current.runs.map((run) => run.id === runId ? change(run) : run),
  })
}
const stop = realtime().subscribe("ai.runs", (payload) => {
  const event = eventOf(payload)
  if (event === null) return
  if (event.kind === "answer") updateRun(event.conversation_id, event.run_id, (run) => ({ ...run, partial_answer: `${run.partial_answer ?? ""}${event.text}` }))
  else if (event.kind === "step") updateRun(event.conversation_id, event.run_id, (run) => ({ ...run, steps: [...(run.steps ?? []).filter((step) => step.ordinal !== event.step.ordinal), event.step].sort((a, b) => a.ordinal - b.ordinal) }))
  else if (event.kind === "reasoning") updateRun(event.conversation_id, event.run_id, (run) => ({ ...run, steps: (run.steps ?? []).map((step) => step.ordinal === event.ordinal ? { ...step, detail: `${step.detail ?? ""}${event.text}` } : step) }))
  else if (event.kind === "run") {
    updateRun(event.conversation_id, event.run_id, (run) => ({ ...run, status: event.status, error: event.error }))
    if (!["running", "awaiting_answer"].includes(event.status)) void queryClient.invalidateQueries({ queryKey: aiConversationKey(event.conversation_id) })
  } else if (event.kind === "title") {
    queryClient.setQueryData<ConversationsPublic>(aiConversationsKey, (current) => current === undefined ? current : { ...current, data: current.data.map((row) => row.id === event.conversation_id ? { ...row, title: event.title } : row) })
  }
  void queryClient.invalidateQueries({ queryKey: aiConversationsKey })
})
onScopeDispose(stop)
</script>

<template>
  <div class="ai-window" data-testid="ai-window-content">
    <aside class="ai-window__rail" :class="{ 'ai-window__rail--collapsed': collapsed }">
      <div class="ai-window__rail-head">
        <AppButton v-if="!collapsed" variant="quiet" layout="navigation" icon="add_comment" label="New chat" data-testid="ai-new-chat" @click="makeConversation" />
        <AppIconButton v-else icon="add_comment" tooltip="New chat" data-testid="ai-new-chat" @click="makeConversation" />
        <AppIconButton :icon="collapsed ? 'chevron_right' : 'chevron_left'" :tooltip="collapsed ? 'Show chat history' : 'Hide chat history'" data-testid="ai-collapse-history" @click="collapsed = !collapsed" />
      </div>
      <div v-if="!collapsed" class="ai-window__history" aria-label="Chat history" data-testid="ai-history">
        <AppSpinner v-if="list.isPending.value" />
        <div v-for="chat in conversations" :key="chat.id" class="ai-window__chat" :class="{ 'ai-window__chat--active': selected === chat.id && !settingsShown }" :data-testid="`ai-chat-row-${chat.id}`" :data-active="selected === chat.id && !settingsShown ? 'true' : 'false'">
          <AppInput v-if="renaming === chat.id" v-model="titleDraft" compact aria-label="Chat title" @keyup.enter="finishRename" @blur="finishRename" />
          <AppButton v-else variant="quiet" layout="navigation" :label="chat.title" :data-testid="`ai-chat-${chat.id}`" @click="select(chat.id)" />
          <span class="ai-window__chat-actions">
            <AppIconButton icon="edit" tooltip="Rename chat" compact @click="beginRename(chat.id, chat.title)" />
            <AppIconButton icon="delete" tooltip="Delete chat" variant="danger-quiet" compact @click="remove(chat.id, chat.title)" />
          </span>
        </div>
      </div>
      <div class="ai-window__rail-foot">
        <AppButton v-if="!collapsed" variant="quiet" layout="navigation" icon="settings" label="Settings" data-testid="ai-open-settings" @click="settingsShown = true" />
        <AppIconButton v-else icon="settings" tooltip="Settings" data-testid="ai-open-settings" @click="settingsShown = true" />
        <AppButton v-if="!collapsed && conversations.length" variant="danger-quiet" size="sm" label="Delete all" data-testid="ai-delete-all" @click="removeAll" />
      </div>
    </aside>
    <main class="ai-window__main">
      <AiSettings v-if="settingsShown" />
      <AiConversation v-else-if="selected" :conversation-id="selected" :key="selected" />
      <div v-else class="ai-window__welcome"><AppButton icon="add_comment" label="New chat" @click="makeConversation" /></div>
    </main>
  </div>
</template>

<style scoped>
.ai-window { height: 100%; min-height: 0; display: flex; background: var(--dp-surface-raised); }
.ai-window__rail { width: 260px; min-width: 180px; display: flex; flex-direction: column; border-right: 1px solid var(--dp-border); background: var(--dp-chrome-raised); }
.ai-window__rail--collapsed { width: 48px; min-width: 48px; }
.ai-window__rail-head, .ai-window__rail-foot { flex: none; display: flex; align-items: center; gap: var(--dp-space-1); padding: var(--dp-space-2); }
.ai-window__rail-head > :first-child, .ai-window__rail-foot > :first-child { flex: 1; }
.ai-window__rail-foot { flex-direction: column; align-items: stretch; border-top: 1px solid var(--dp-border); }
.ai-window__rail--collapsed .ai-window__rail-head { flex-direction: column; }
.ai-window__history { flex: 1; min-height: 0; overflow: auto; padding: var(--dp-space-1); }
.ai-window__chat { display: flex; align-items: center; border-radius: var(--dp-radius-control); }
.ai-window__chat--active { background: var(--dp-active); }
.ai-window__chat > :first-child { flex: 1; min-width: 0; }
.ai-window__chat-actions { display: none; flex: none; }
.ai-window__chat:hover .ai-window__chat-actions, .ai-window__chat:focus-within .ai-window__chat-actions { display: flex; }
.ai-window__main { flex: 1; min-width: 0; min-height: 0; }
.ai-window__welcome { height: 100%; display: grid; place-items: center; }
</style>
