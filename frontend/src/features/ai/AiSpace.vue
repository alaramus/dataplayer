<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, onMounted, onScopeDispose, ref, watch } from "vue"

import type { AgentRunPublic, AgentStepPublic, ConversationPublic, ConversationsPublic } from "@/client"
import { AppButton, AppIconButton, AppInput, AppSpinner, useConfirm, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
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

import AiChatRow from "./AiChatRow.vue"
import AiConversation from "./AiConversation.vue"
import AiSettings from "./AiSettings.vue"
import {
  aiConversationKey,
  aiConversationsKey,
  useAiConversations,
  useAiProjects,
  useCreateAiConversation,
  useCreateAiProject,
  useDeleteAiProject,
  useRenameAiProject,
  useUpdateAiConversation,
} from "./api"
import { rememberAiConversation, rememberedAiConversation, requestedAiConversation } from "./state"
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
const projectList = useAiProjects()
const createConversation = useCreateAiConversation()
const updateConversation = useUpdateAiConversation()
const createProject = useCreateAiProject()
const renameProject = useRenameAiProject()
const deleteProject = useDeleteAiProject()
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

// The header button collapses the first panel of the space being shown
// through one shape; here that is the chat-history rail.
defineExpose({
  toggleFirstPanel: () => { collapsed.value = !collapsed.value },
  firstPanelCollapsed: computed(() => collapsed.value),
})
const renaming = ref<string | null>(null)
const titleDraft = ref("")

const conversations = computed(() => list.data.value?.data ?? [])
const selectedChat = computed(() => conversations.value.find((chat) => chat.id === selected.value) ?? null)
const projects = computed(() => projectList.data.value?.data ?? [])
const closedProjects = ref(new Set<string>())
const projectDialogShown = ref(false)
const projectDraft = ref("")
// Which project the dialog is renaming, or the chat a new one is being made
// for — the two things the one dialog is opened for.
const renamingProject = ref<string | null>(null)
const projectFor = ref<string | null>(null)

/**
 * The history as it is drawn: every folder in turn, then what is in no folder.
 *
 * A folder stays on screen while it is empty, or making one for a chat that is
 * not in it yet would make it disappear before it could be used.
 */
const grouped = computed(() => {
  const groups = projects.value.map((project) => ({
    id: project.id as string | null,
    name: project.name,
    chats: conversations.value.filter((chat) => chat.project_id === project.id),
  }))
  return [
    ...groups,
    { id: null, name: "", chats: conversations.value.filter((chat) => !chat.project_id) },
  ].filter((group) => group.id !== null || group.chats.length > 0)
})

function toggleProject(id: string) {
  const next = new Set(closedProjects.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  closedProjects.value = next
}
function beginProjectFor(chatId: string | null) {
  renamingProject.value = null
  projectFor.value = chatId
  projectDraft.value = ""
  projectDialogShown.value = true
}
function beginProjectRename(id: string, name: string) {
  renamingProject.value = id
  projectFor.value = null
  projectDraft.value = name
  projectDialogShown.value = true
}
async function saveProject() {
  const name = projectDraft.value.trim()
  if (!name) return
  const renaming = renamingProject.value
  try {
    if (renaming !== null) {
      await renameProject.mutateAsync({ id: renaming, name })
    } else {
      const made = await createProject.mutateAsync(name)
      // A folder made from a chat's own menu is made to put that chat in.
      if (projectFor.value !== null) await moveChat(projectFor.value, made.id)
    }
    projectDialogShown.value = false
  }
  catch (cause) { toast.error(messageOf(cause, "The project could not be saved")) }
}
async function removeProject(id: string, name: string) {
  if (!(await confirm({
    title: "Delete project?",
    message: `“${name}” will be deleted. The chats in it are kept.`,
    confirmLabel: "Delete",
    danger: true,
  }))) return
  try { await deleteProject.mutateAsync(id) }
  catch (cause) { toast.error(messageOf(cause, "The project could not be deleted")) }
}
async function moveChat(id: string, projectId: string | null) {
  try { await updateConversation.mutateAsync({ id, project_id: projectId }) }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be moved")) }
}

watch(conversations, (rows) => {
  if (selected.value !== null && rows.some((row) => row.id === selected.value)) return
  // Trap: the list is empty while it loads; falling back to the first row then drops the
  // remembered selection and erases it from storage, so restore after reload lands on
  // whatever row the server lists first.
  if (list.isPending.value) return
  selected.value = rows[0]?.id ?? null
}, { immediate: true })
watch(selected, (id) => rememberAiConversation(id))
// A Needs-you row names its chat; opening the sheet's space is not enough (D113).
watch(requestedAiConversation, (id) => {
  if (id === null) return
  selected.value = id
  settingsShown.value = false
  requestedAiConversation.value = null
})

async function makeConversation() {
  try { const created = await createConversation.mutateAsync(); selected.value = created.id; settingsShown.value = false }
  catch (cause) { toast.error(messageOf(cause, "A new chat could not be created")) }
}
function select(id: string) { selected.value = id; settingsShown.value = false }
function beginRename(id: string, title: string) { renaming.value = id; titleDraft.value = title }
async function finishRename() {
  const id = renaming.value
  const title = titleDraft.value.trim()
  if (id === null) return
  // An emptied field is a cancelled rename, not a chat called nothing.
  if (!title) { renaming.value = null; return }
  try { await updateConversation.mutateAsync({ id, title }); renaming.value = null }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be renamed")) }
}
async function setPinned(id: string, pinned: boolean) {
  try { await updateConversation.mutateAsync({ id, pinned }) }
  catch (cause) { toast.error(messageOf(cause, pinned ? "The chat could not be pinned" : "The chat could not be unpinned")) }
}
// Archiving is not deleting: it is offered without a confirmation and taken
// back from the message it leaves. What is in the archive is deleted in the
// settings, which is the only place that can (D141).
async function archive(id: string) {
  try {
    await updateConversation.mutateAsync({ id, archived: true })
    toast.offer("Chat archived", { label: "Undo", onClick: () => { void restore(id) } })
  }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be archived")) }
}
async function restore(id: string) {
  try { await updateConversation.mutateAsync({ id, archived: false }); selected.value = id }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be restored")) }
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
        <!-- The header button collapses this rail; no chevron of its own. -->
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
          icon="create_new_folder"
          tooltip="New project"
          data-testid="ai-new-project"
          @click="beginProjectFor(null)"
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
          v-for="group in grouped"
          :key="group.id ?? 'loose'"
          class="ai-window__group"
          :data-testid="group.id ? `ai-project-${group.id}` : 'ai-loose-chats'"
        >
          <div
            v-if="group.id !== null"
            class="ai-window__project"
          >
            <button
              type="button"
              class="ai-window__project-name"
              :aria-expanded="!closedProjects.has(group.id)"
              :title="group.name"
              :data-testid="`ai-project-toggle-${group.id}`"
              @click="toggleProject(group.id)"
            >
              <q-icon
                :name="closedProjects.has(group.id) ? 'chevron_right' : 'expand_more'"
                size="16px"
              />
              <span class="ai-window__project-title">{{ group.name }}</span>
              <span class="ai-window__project-count">{{ group.chats.length }}</span>
            </button>
            <span class="ai-window__project-actions">
              <AppIconButton
                icon="edit"
                tooltip="Rename project"
                compact
                :data-testid="`ai-project-rename-${group.id}`"
                @click="beginProjectRename(group.id, group.name)"
              />
              <AppIconButton
                icon="delete"
                tooltip="Delete project"
                variant="danger-quiet"
                compact
                :data-testid="`ai-project-delete-${group.id}`"
                @click="removeProject(group.id, group.name)"
              />
            </span>
          </div>
          <div
            v-if="group.id === null || !closedProjects.has(group.id)"
            :class="{ 'ai-window__project-chats': group.id !== null }"
          >
            <AiChatRow
              v-for="chat in group.chats"
              :key="chat.id"
              :chat="chat"
              :active="selected === chat.id && !settingsShown"
              :projects="projects"
              @select="select(chat.id)"
              @pin="setPinned(chat.id, $event)"
              @archive="archive(chat.id)"
              @move="moveChat(chat.id, $event)"
              @new-project="beginProjectFor(chat.id)"
            />
          </div>
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
      <!-- The open chat is named where the eye already is; pressing the name
           is how a chat is renamed. -->
      <div
        v-if="selectedChat !== null && !settingsShown"
        class="ai-window__head"
        data-testid="ai-chat-head"
      >
        <AppInput
          v-if="renaming === selectedChat.id"
          v-model="titleDraft"
          compact
          aria-label="Chat title"
          data-testid="ai-rename-input"
          @keyup.enter="finishRename"
          @keyup.escape="renaming = null"
          @blur="finishRename"
        />
        <button
          v-else
          type="button"
          class="ai-window__head-title"
          :title="`Rename “${selectedChat.title}”`"
          data-testid="ai-chat-heading"
          @click="beginRename(selectedChat.id, selectedChat.title)"
        >
          {{ selectedChat.title }}
        </button>
      </div>
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
    <WindowDialog
      v-model="projectDialogShown"
      :title="renamingProject === null ? 'New project' : 'Rename project'"
      size="sm"
      data-testid="ai-project-dialog"
    >
      <AppInput
        v-model="projectDraft"
        label="Name"
        data-testid="ai-project-name"
        @keyup.enter="saveProject"
      />
      <template #actions>
        <AppButton
          variant="quiet"
          label="Cancel"
          @click="projectDialogShown = false"
        />
        <AppButton
          :label="renamingProject === null ? 'Create' : 'Rename'"
          :disable="!projectDraft.trim()"
          data-testid="ai-project-save"
          @click="saveProject"
        />
      </template>
    </WindowDialog>
  </div>
</template>

<style scoped>
.ai-space { width: 100%; height: 100%; min-height: 0; display: flex; overflow: hidden; }
.ai-window__card { min-width: 0; min-height: 0; overflow: hidden; border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface); }
.ai-window__rail { flex-grow: 0; flex-shrink: 0; display: flex; flex-direction: column; }
.ai-window__rail-head, .ai-window__rail-foot { flex: none; display: flex; align-items: center; gap: var(--dp-space-1); padding: var(--dp-space-2); }
.ai-window__rail-head > :first-child, .ai-window__rail-foot > :first-child { flex: 1; }
.ai-window__rail-foot { flex-direction: column; align-items: stretch; border-top: 1px solid var(--dp-border); }
.ai-window__rail--collapsed .ai-window__rail-head { flex-direction: column; }
/* The collapsed rail takes the same forty pixels a collapsed workspace column
   or the dashboards rail does; the wide rail's padding would push past it. */
.ai-window__rail--collapsed .ai-window__rail-head, .ai-window__rail--collapsed .ai-window__rail-foot { align-items: center; padding-right: 0; padding-left: 0; }
.ai-window__history { flex: 1; min-height: 0; overflow: auto; padding: var(--dp-space-1); }
.ai-window__project { display: flex; align-items: center; }
.ai-window__project-name { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--dp-space-1); border: 0; padding: var(--dp-space-1); background: transparent; color: var(--dp-text-muted); font: inherit; font-weight: 600; cursor: pointer; }
.ai-window__project-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-window__project-count { flex: none; color: var(--dp-text-faint); font-weight: 400; }
.ai-window__project-actions { display: none; flex: none; }
.ai-window__project:hover .ai-window__project-actions, .ai-window__project:focus-within .ai-window__project-actions { display: flex; }
/* The chats of a folder are stepped in under its name, which is the whole way
   a reader sees what is in it. */
.ai-window__project-chats { padding-left: var(--dp-space-3); }
.ai-window__main { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.ai-window__head { flex: none; display: flex; align-items: center; height: var(--dp-tab-strip-height); padding: 0 var(--dp-space-3); border-bottom: 1px solid var(--dp-border-faint); }
/* Trap: a dense Quasar field's control is 40px, taller than this strip, so
   pressing the name grew the header by eight pixels and pushed the whole
   conversation down. The field takes the strip's height and the heading's
   type, so renaming moves nothing. */
.ai-window__head :deep(.q-field) { font-size: inherit; }
.ai-window__head :deep(.q-field__control) { height: var(--dp-tab-strip-height); }
.ai-window__head :deep(.q-field__native) { padding: 0; font-weight: 600; line-height: var(--dp-tab-strip-height); }
.ai-window__head > :first-child { flex: 1; min-width: 0; }
.ai-window__head-title { max-width: 100%; overflow: hidden; border: 0; padding: 0; background: transparent; color: var(--dp-text-strong); font: inherit; font-weight: 600; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: text; }
.ai-window__welcome { flex: 1; display: grid; place-items: center; }
</style>
