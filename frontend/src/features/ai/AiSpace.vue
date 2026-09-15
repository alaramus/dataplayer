<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, onMounted, onScopeDispose, ref, watch } from "vue"

import type { AgentRunPublic, AgentStepPublic, ConversationPublic, ConversationsPublic } from "@/client"
import { AppButton, AppIconButton, AppInput, AppSpinner, useConfirm, useToast } from "@/shared/ui"
import { realtime } from "@/shared/realtime/client"
import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import { WorkspaceSeparator } from "@/shared/workspace"
import {
  clampRailWidth,
  parseRailNarrow,
  parseRailWidth,
  RAIL_NARROW_PX,
} from "@/shared/workspace/railWidth"

import AiConversation from "./AiConversation.vue"
import AiSettings from "./AiSettings.vue"
import { aiConversationKey, aiConversationsKey, useAiConversations, useCreateAiConversation, useDeleteAiConversation, useDeleteAllAiConversations, useRenameAiConversation } from "./api"
import { rememberAiConversation, rememberedAiConversation } from "./state"
import type { AiOpenIntent } from "./context"

defineProps<{ contexts: import("@/client").ScreenContext[] }>()
const emit = defineEmits<{ open: [intent: AiOpenIntent] }>()

type AiEvent =
  | { kind: "run"; conversation_id: string; run_id: string; status: AgentRunPublic["status"]; error?: string | null }
  | { kind: "step"; conversation_id: string; run_id: string; step: AgentStepPublic }
  | { kind: "answer"; conversation_id: string; run_id: string; text: string }
  | { kind: "reasoning"; conversation_id: string; run_id: string; ordinal: number; text: string }
  | { kind: "title"; conversation_id: string; title: string }
  | { kind: "open"; conversation_id: string; intent: AiOpenIntent }

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
const RAIL_WIDTH_KEY = "dataplayer-ai-rail"
const RAIL_NARROW_KEY = "dataplayer-ai-rail-narrow"
function stored(key: string): string | null {
  try { return localStorage.getItem(serverStorageKey(key)) } catch { return null }
}
function store(key: string, value: string) {
  try { localStorage.setItem(serverStorageKey(key), value) } catch { /* Resizing still works. */ }
}
const spaceElement = ref<HTMLElement | null>(null)
const spaceWidth = ref(0)
const railWidth = ref(parseRailWidth(stored(RAIL_WIDTH_KEY)))
const collapsed = ref(parseRailNarrow(stored(RAIL_NARROW_KEY)))
const shownRailWidth = computed(() => collapsed.value
  ? RAIL_NARROW_PX
  : clampRailWidth(railWidth.value, spaceWidth.value))
const observer = new ResizeObserver((entries) => {
  const entry = entries[0]
  if (entry !== undefined) spaceWidth.value = entry.contentRect.width
})
onMounted(() => { if (spaceElement.value !== null) observer.observe(spaceElement.value) })
onBeforeUnmount(() => observer.disconnect())
function resizeRail(deltaPx: number) {
  if (!collapsed.value) railWidth.value = clampRailWidth(shownRailWidth.value + deltaPx, spaceWidth.value)
}
function pressGap() {
  if (collapsed.value) collapsed.value = false
}
watch(railWidth, (width) => store(RAIL_WIDTH_KEY, String(width)))
watch(collapsed, (narrow) => store(RAIL_NARROW_KEY, narrow ? "narrow" : "wide"))
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
    if (event.status === "awaiting_answer" || !["running", "awaiting_answer"].includes(event.status)) {
      void queryClient.invalidateQueries({ queryKey: aiConversationKey(event.conversation_id) })
    }
  } else if (event.kind === "title") {
    queryClient.setQueryData<ConversationsPublic>(aiConversationsKey, (current) => current === undefined ? current : { ...current, data: current.data.map((row) => row.id === event.conversation_id ? { ...row, title: event.title } : row) })
  } else if (event.kind === "open") {
    emit("open", event.intent)
  }
  void queryClient.invalidateQueries({ queryKey: aiConversationsKey })
})
onScopeDispose(stop)
</script>

<template>
  <div
    ref="spaceElement"
    class="ai-space"
    data-testid="ai-space"
  >
    <aside
      class="ai-window__card ai-window__rail"
      :class="{ 'ai-window__rail--collapsed': collapsed }"
      :style="{ flexBasis: `${String(shownRailWidth)}px` }"
      data-testid="ai-rail"
    >
      <div class="ai-window__rail-head">
        <AppButton
          v-if="!collapsed"
          variant="quiet"
          layout="navigation"
          icon="add_comment"
          label="New chat"
          data-testid="ai-new-chat"
          @click="makeConversation"
        />
        <AppIconButton
          v-else
          icon="add_comment"
          tooltip="New chat"
          data-testid="ai-new-chat"
          @click="makeConversation"
        />
        <AppIconButton
          :icon="collapsed ? 'chevron_right' : 'chevron_left'"
          :tooltip="collapsed ? 'Show chat history' : 'Hide chat history'"
          data-testid="ai-collapse-history"
          @click="collapsed = !collapsed"
        />
      </div>
      <div
        v-if="!collapsed"
        class="ai-window__history"
        aria-label="Chat history"
        data-testid="ai-history"
      >
        <AppSpinner v-if="list.isPending.value" />
        <div
          v-for="chat in conversations"
          :key="chat.id"
          class="ai-window__chat"
          :class="{ 'ai-window__chat--active': selected === chat.id && !settingsShown }"
          :data-testid="`ai-chat-row-${chat.id}`"
          :data-active="selected === chat.id && !settingsShown ? 'true' : 'false'"
        >
          <AppInput
            v-if="renaming === chat.id"
            v-model="titleDraft"
            compact
            aria-label="Chat title"
            @keyup.enter="finishRename"
            @blur="finishRename"
          />
          <AppButton
            v-else
            variant="quiet"
            layout="navigation"
            :label="chat.title"
            :data-testid="`ai-chat-${chat.id}`"
            @click="select(chat.id)"
          />
          <span class="ai-window__chat-actions">
            <AppIconButton
              icon="edit"
              tooltip="Rename chat"
              compact
              @click="beginRename(chat.id, chat.title)"
            />
            <AppIconButton
              icon="delete"
              tooltip="Delete chat"
              variant="danger-quiet"
              compact
              @click="remove(chat.id, chat.title)"
            />
          </span>
        </div>
      </div>
      <div class="ai-window__rail-foot">
        <AppButton
          v-if="!collapsed"
          variant="quiet"
          layout="navigation"
          icon="settings"
          label="Settings"
          data-testid="ai-open-settings"
          @click="settingsShown = true"
        />
        <AppIconButton
          v-else
          icon="settings"
          tooltip="Settings"
          data-testid="ai-open-settings"
          @click="settingsShown = true"
        />
        <AppButton
          v-if="!collapsed && conversations.length"
          variant="danger-quiet"
          size="sm"
          label="Delete all"
          data-testid="ai-delete-all"
          @click="removeAll"
        />
      </div>
    </aside>
    <WorkspaceSeparator
      direction="row"
      @move="resizeRail"
      @toggle="pressGap"
    />
    <main
      class="ai-window__card ai-window__main"
      data-testid="ai-conversation-card"
    >
      <AiSettings v-if="settingsShown" />
      <AiConversation
        v-else-if="selected"
        :key="selected"
        :conversation-id="selected"
        :contexts="contexts"
      />
      <div
        v-else
        class="ai-window__welcome"
      >
        <AppButton
          icon="add_comment"
          label="New chat"
          @click="makeConversation"
        />
      </div>
    </main>
  </div>
</template>

<style scoped>
.ai-space { width: 100%; height: 100%; min-height: 0; display: flex; overflow: hidden; }
.ai-window__card { min-width: 0; min-height: 0; overflow: hidden; border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface); }
.ai-window__rail { flex-grow: 0; flex-shrink: 0; display: flex; flex-direction: column; }
.ai-window__rail--collapsed { min-width: 48px; }
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
