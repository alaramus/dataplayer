<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { useQueryClient } from "@tanstack/vue-query"
import { computed, nextTick, onScopeDispose, ref, watch } from "vue"

import type { AgentRunPublic, AgentStepPublic, ConversationPublic, ConversationsPublic, ConversationSummary, QuickChatSummary } from "@/client"
import {
  AppButton,
  AppCardFrame,
  AppCardHead,
  AppEmptyState,
  AppIconButton,
  AppForm,
  AppInput,
  AppSpinner,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
import { realtime } from "@/shared/realtime/client"
import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import { WorkspaceSeparator } from "@/shared/workspace"
import { useSideRail } from "@/shared/workspace/useSideRail"

import AiChatRow from "./AiChatRow.vue"
import AiConversation from "./AiConversation.vue"
import AiSettings from "./AiSettings.vue"
import {
  aiConversationKey,
  aiConversationsKey,
  useAiConversations,
  useAiProjects,
  useQuickChats,
  useCreateAiProject,
  useDeleteAiProject,
  useRenameAiProject,
  useUpdateAiConversation,
  useUpdateQuickChat,
} from "./api"
import { freshProjectName } from "./projectName"
import { hasAiDraft } from "./draft"
import { openQuickChat } from "./quickChatLauncher"
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
const quickList = useQuickChats()
const projectList = useAiProjects()
const updateConversation = useUpdateAiConversation()
const updateQuickChat = useUpdateQuickChat()
const createProject = useCreateAiProject()
const renameProject = useRenameAiProject()
const deleteProject = useDeleteAiProject()
const queryClient = useQueryClient()
const confirm = useConfirm()
const toast = useToast()
const newDraftOpen = ref(hasAiDraft(serverStorageKey("new-agent-chat")))
const selected = ref<string | null>(newDraftOpen.value ? null : rememberedAiConversation())
const settingsShown = ref(false)
const spaceElement = ref<HTMLElement | null>(null)
const {
  narrow: collapsed,
  shownWidth: shownRailWidth,
  resize: resizeRail,
  pressGap,
} = useSideRail(spaceElement, {
  width: serverStorageKey("dataplayer-ai-rail"),
  narrow: serverStorageKey("dataplayer-ai-rail-narrow"),
})

// The header button collapses the first panel of the space being shown
// through one shape; here that is the chat-history rail.
defineExpose({
  toggleFirstPanel: () => { collapsed.value = !collapsed.value },
  firstPanelCollapsed: computed(() => collapsed.value),
})
/** The chat the rename window is open for, as the dashboards' is (one gesture for both). */
const renaming = ref<string | null>(null)
const renameShown = ref(false)
const titleDraft = ref("")
const chatNameFilter = ref("")
const chatFilterOpen = ref(false)
const chatFilterField = ref<InstanceType<typeof AppInput> | null>(null)
const filterClosedProjects = ref(new Set<string>())

async function openChatFilter() {
  chatFilterOpen.value = true
  await nextTick()
  ;(chatFilterField.value?.$el as HTMLElement | undefined)?.querySelector("input")?.focus()
}
function closeChatFilter() {
  chatNameFilter.value = ""
  chatFilterOpen.value = false
  filterClosedProjects.value = new Set()
}

const conversations = computed(() => list.data.value?.data ?? [])
// The history is one list merged from two queries. Drawn before both arrive,
// it reorders when the second one lands, under a row about to be clicked.
const historyLoading = computed(() => list.isPending.value || quickList.isPending.value)
type HistoryChat = { kind: "agent"; chat: ConversationSummary } | { kind: "quick"; chat: QuickChatSummary }
const byRecent = (a: HistoryChat, b: HistoryChat) =>
  (b.chat.updated_at ?? "").localeCompare(a.chat.updated_at ?? "")
/** The pinned chats' folder, folded like a project's under this key. */
const PINNED = "pinned"
interface HistoryGroup {
  kind: "pinned" | "project" | "loose"
  /** What folds it: a project's id, `PINNED`, or null for the loose chats. */
  id: string | null
  name: string
  chats: HistoryChat[]
}
const selectedChat = computed(() => conversations.value.find((chat) => chat.id === selected.value) ?? null)
const projects = computed(() => projectList.data.value?.data ?? [])
const closedProjects = ref(new Set<string>())
const projectDialogShown = ref(false)
const projectDraft = ref("")
// Which project the dialog is renaming, or the chat a new one is being made
// for — the two things the one dialog is opened for.
const renamingProject = ref<string | null>(null)
const projectFor = ref<HistoryChat | null>(null)

/**
 * The history as it is drawn: the pinned chats, every project in turn, then
 * what is in no folder. A pinned chat is never in a project; the server holds
 * that, so the two never claim one chat.
 *
 * A project stays on screen while it is empty, or making one for a chat that
 * is not in it yet would make it disappear before it could be used. The
 * pinned folder goes with its last chat: nobody makes it.
 */
const grouped = computed<HistoryGroup[]>(() => {
  const chats = [
    ...conversations.value.map((chat): HistoryChat => ({ kind: "agent", chat })),
    ...(quickList.data.value ?? []).map((chat): HistoryChat => ({ kind: "quick", chat })),
  ].sort(byRecent)
  const pinned = chats.filter((entry) => entry.chat.pinned === true)
  const unpinned = chats.filter((entry) => entry.chat.pinned !== true)
  return [
    ...(pinned.length > 0 ? [{ kind: "pinned" as const, id: PINNED, name: "Pinned", chats: pinned }] : []),
    ...projects.value.map((project) => ({
      kind: "project" as const,
      id: project.id,
      name: project.name,
      chats: unpinned.filter((entry) => entry.chat.project_id === project.id),
    })),
    { kind: "loose" as const, id: null, name: "", chats: unpinned.filter((entry) => !entry.chat.project_id) },
  ].filter((group) => group.kind === "project" || group.chats.length > 0)
})
const visibleGroups = computed(() => {
  const query = chatNameFilter.value.trim().toLocaleLowerCase()
  if (!query) return grouped.value
  return grouped.value
    .map((group) => ({
      ...group,
      chats: group.name.toLocaleLowerCase().includes(query)
        ? group.chats
        : group.chats.filter((entry) => entry.chat.title.toLocaleLowerCase().includes(query)),
    }))
    .filter((group) => group.name.toLocaleLowerCase().includes(query) || group.chats.length > 0)
})

function toggleProject(id: string) {
  const target = chatNameFilter.value.trim() ? filterClosedProjects : closedProjects
  const next = new Set(target.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  target.value = next
}
function projectIsClosed(id: string) {
  return chatNameFilter.value.trim() ? filterClosedProjects.value.has(id) : closedProjects.value.has(id)
}
function beginProjectFor(entry: HistoryChat | null) {
  renamingProject.value = null
  projectFor.value = entry
  projectDraft.value = freshProjectName(projects.value.map((project) => project.name))
  projectDialogShown.value = true
}
/**
 * A name in a field is selected as it gets focus, so typing replaces it: a
 * name is replaced more often than edited.
 */
const projectField = ref<InstanceType<typeof AppInput> | null>(null)
const renameField = ref<InstanceType<typeof AppInput> | null>(null)
function selectAllIn(field: InstanceType<typeof AppInput> | null) {
  ;(field?.$el as HTMLElement | undefined)?.querySelector("input")?.select()
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
  const held = grouped.value.find((group) => group.id === id)?.chats.length ?? 0
  const one = held === 1
  let chats: "keep" | "archive" = "keep"
  if (!(await confirm({
    title: "Delete project?",
    message: held === 0
      ? `“${name}” will be deleted.`
      : `“${name}” will be deleted. ${one ? "Where does its chat go?" : `Where do its ${String(held)} chats go?`}`,
    confirmLabel: "Delete",
    danger: true,
    ...(held === 0 ? {} : {
      choices: [
        {
          value: "keep",
          label: `Move ${one ? "it" : "them"} to the chat list`,
          description: `${one ? "It stays" : "They stay"} in the history, in no project`,
        },
        { value: "archive", label: `Archive ${one ? "it" : "them"}`, description: "Restored or deleted later in Settings" },
      ],
      onChoice: (value: string) => { chats = value === "archive" ? "archive" : "keep" },
    }),
  }))) return
  try { await deleteProject.mutateAsync({ id, chats }) }
  catch (cause) { toast.error(messageOf(cause, "The project could not be deleted")) }
}
async function moveChat(entry: HistoryChat, projectId: string | null) {
  try {
    if (entry.kind === "agent") await updateConversation.mutateAsync({ id: entry.chat.id, project_id: projectId })
    else await updateQuickChat.mutateAsync({ id: entry.chat.id, project_id: projectId })
  }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be moved")) }
}

watch(conversations, (rows) => {
  if (newDraftOpen.value) return
  if (selected.value !== null && rows.some((row) => row.id === selected.value)) return
  // Trap: the list is empty while it loads; falling back to the first row then drops the
  // remembered selection and erases it from storage, so restore after reload lands on
  // whatever row the server lists first.
  if (list.isPending.value || list.data.value === undefined) return
  // A person with no agent conversations should land on the composer, not on a
  // welcome button that asks them to open the composer separately.
  if (rows.length === 0) {
    newDraftOpen.value = true
    selected.value = null
    return
  }
  selected.value = rows[0]?.id ?? null
}, { immediate: true })
watch(selected, (id) => rememberAiConversation(id))
// A Needs-you row names its chat; opening the sheet's space is not enough (D113).
watch(requestedAiConversation, (id) => {
  if (id === null) return
  newDraftOpen.value = false
  selected.value = id
  settingsShown.value = false
  requestedAiConversation.value = null
})

// Settings cover the conversation rather than replacing it: pressing the entry
// again puts back the chat that was open, which is still the selected one.
function toggleSettings() { settingsShown.value = !settingsShown.value }

/** The project the open draft will be made in, while it still exists. */
const draftProjectId = ref<string | null>(null)
const draftProject = computed(() => projects.value.find((project) => project.id === draftProjectId.value) ?? null)
function makeConversation() {
  draftProjectId.value = null
  if (newDraftOpen.value) return
  newDraftOpen.value = true
  selected.value = null
  settingsShown.value = false
}
/** A draft made from a project's row, opened so the chat is seen landing in it. */
function makeConversationIn(projectId: string) {
  makeConversation()
  draftProjectId.value = projectId
  for (const target of [closedProjects, filterClosedProjects]) {
    if (!target.value.has(projectId)) continue
    const next = new Set(target.value)
    next.delete(projectId)
    target.value = next
  }
}
function select(id: string) { newDraftOpen.value = false; selected.value = id; settingsShown.value = false }
function startedConversation(id: string) {
  newDraftOpen.value = false
  selected.value = id
}
function selectHistory(entry: HistoryChat) {
  if (entry.kind === "agent") select(entry.chat.id)
  else openQuickChat({ kind: "chat", id: entry.chat.id })
}
function pinHistory(entry: HistoryChat, pinned: boolean) {
  if (entry.kind === "agent") void setPinned(entry.chat.id, pinned)
  else void setQuickPinned(entry.chat.id, pinned)
}
function archiveHistory(entry: HistoryChat) {
  if (entry.kind === "agent") void archive(entry.chat.id)
  else void archiveQuick(entry.chat.id)
}
function beginRename(id: string, title: string) {
  renaming.value = id
  titleDraft.value = title
  renameShown.value = true
}
async function finishRename() {
  const id = renaming.value
  const title = titleDraft.value.trim()
  if (id === null || !title) return
  try { await updateConversation.mutateAsync({ id, title }); renameShown.value = false }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be renamed")) }
}
async function setPinned(id: string, pinned: boolean) {
  try { await updateConversation.mutateAsync({ id, pinned }) }
  catch (cause) { toast.error(messageOf(cause, pinned ? "The chat could not be pinned" : "The chat could not be unpinned")) }
}
async function setQuickPinned(id: string, pinned: boolean) {
  try { await updateQuickChat.mutateAsync({ id, pinned }) }
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
async function archiveQuick(id: string) {
  try {
    await updateQuickChat.mutateAsync({ id, archived: true })
    toast.offer("Chat archived", { label: "Undo", onClick: () => { void restoreQuick(id) } })
  }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be archived")) }
}
async function restoreQuick(id: string) {
  try { await updateQuickChat.mutateAsync({ id, archived: false }) }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be restored")) }
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
    <AppCardFrame
      tag="aside"
      class="ai-window__rail"
      :class="{ 'ai-window__rail--collapsed': collapsed }"
      :style="{ flexBasis: `${String(shownRailWidth)}px` }"
      data-testid="ai-rail"
    >
      <!-- The header button collapses this rail; no chevron of its own. -->
      <AppCardHead
        v-if="!collapsed && chatFilterOpen"
        class="ai-window__filter-head"
        @keydown.esc.stop="closeChatFilter"
      >
        <AppInput
          ref="chatFilterField"
          v-model="chatNameFilter"
          compact
          placeholder="Filter chats"
          aria-label="Filter chats and projects by name"
          autocomplete="off"
          data-testid="ai-name-filter"
        />
        <template #actions>
          <AppIconButton
            :icon="appIcons.close"
            tooltip="Close chat filter"
            data-testid="ai-filter-close"
            @click="closeChatFilter"
          />
        </template>
      </AppCardHead>
      <AppCardHead
        v-else-if="!collapsed"
        title="Chats"
      >
        <template #actions>
          <AppIconButton
            :icon="appIcons.add"
            tooltip="New chat"
            data-testid="ai-new-chat"
            @click="makeConversation"
          />
          <AppIconButton
            :icon="appIcons.search"
            tooltip="Filter chats and projects by name"
            data-testid="ai-filter-open"
            @click="openChatFilter"
          />
          <AppIconButton
            :icon="appIcons.createNewFolder"
            tooltip="New project"
            data-testid="ai-new-project"
            @click="beginProjectFor(null)"
          />
        </template>
      </AppCardHead>
      <!-- Collapsed, the plus alone in the head, as the collapsed column of
           connections and the dashboards rail keep it: a project is made
           beside the history, which is not drawn at this width. -->
      <AppCardHead
        v-else
        class="ai-window__rail-head"
        data-testid="ai-rail-head"
      >
        <AppIconButton
          :icon="appIcons.add"
          tooltip="New chat"
          data-testid="ai-new-chat"
          @click="makeConversation"
        />
      </AppCardHead>
      <div
        v-if="!collapsed"
        class="ai-window__history"
        aria-label="Chat history"
        :aria-busy="historyLoading"
        data-testid="ai-history"
      >
        <AppSpinner v-if="historyLoading" />
        <AppEmptyState
          v-else-if="chatNameFilter.trim() && visibleGroups.length === 0"
          text="No matching chats or projects"
        />
        <template v-else>
          <div
            v-for="(group, index) in visibleGroups"
            :key="group.id ?? 'loose'"
            class="ai-window__group"
            :data-testid="group.kind === 'project' ? `ai-project-${group.id}` : `ai-${group.kind}-chats`"
          >
            <!-- A line where the pinned folder, the projects and the loose
                 chats meet, not between one project and the next. -->
            <div
              v-if="index > 0 && visibleGroups[index - 1]?.kind !== group.kind"
              class="ai-window__group-rule"
              role="separator"
            />
            <div
              v-if="group.id !== null"
              class="ai-window__project"
            >
              <button
                type="button"
                class="ai-window__project-name"
                :aria-expanded="!projectIsClosed(group.id)"
                :title="group.name"
                :data-testid="group.kind === 'project' ? `ai-project-toggle-${group.id}` : 'ai-pinned-toggle'"
                @click="toggleProject(group.id)"
              >
                <q-icon
                  :name="projectIsClosed(group.id) ? 'chevron_right' : 'keyboard_arrow_down'"
                  size="var(--dp-icon-sm)"
                />
                <span class="ai-window__project-title">{{ group.name }}</span>
                <span
                  v-if="group.chats.length > 0"
                  class="ai-window__project-count"
                >({{ group.chats.length }})</span>
              </button>
              <span
                v-if="group.kind === 'project'"
                class="ai-window__project-actions"
              >
                <AppIconButton
                  :icon="appIcons.add"
                  tooltip="New chat in this project"
                  compact
                  :data-testid="`ai-project-new-chat-${group.id}`"
                  @click="makeConversationIn(group.id)"
                />
                <AppIconButton
                  :icon="appIcons.edit"
                  tooltip="Rename project"
                  compact
                  :data-testid="`ai-project-rename-${group.id}`"
                  @click="beginProjectRename(group.id, group.name)"
                />
                <AppIconButton
                  :icon="appIcons.delete"
                  tooltip="Delete project"
                  variant="danger-quiet"
                  compact
                  :data-testid="`ai-project-delete-${group.id}`"
                  @click="removeProject(group.id, group.name)"
                />
              </span>
            </div>
            <div
              v-if="group.id === null || !projectIsClosed(group.id)"
              :class="{ 'ai-window__project-chats': group.id !== null }"
            >
              <AiChatRow
                v-for="entry in group.chats"
                :key="`${entry.kind}-${entry.chat.id}`"
                :chat="entry.chat"
                :active="entry.kind === 'agent' && selected === entry.chat.id && !settingsShown"
                :projects="projects"
                @select="selectHistory(entry)"
                @pin="pinHistory(entry, $event)"
                @archive="archiveHistory(entry)"
                @move="moveChat(entry, $event)"
                @new-project="beginProjectFor(entry)"
              />
            </div>
          </div>
        </template>
      </div>
      <div class="ai-window__rail-foot">
        <AppButton
          v-if="!collapsed"
          variant="quiet"
          layout="navigation"
          :icon="appIcons.settings"
          label="Settings"
          :aria-pressed="settingsShown"
          data-testid="ai-open-settings"
          @click="toggleSettings"
        />
        <AppIconButton
          v-else
          :icon="appIcons.settings"
          tooltip="Settings"
          :aria-pressed="settingsShown"
          data-testid="ai-open-settings"
          @click="toggleSettings"
        />
      </div>
    </AppCardFrame>
    <WorkspaceSeparator
      direction="row"
      @move="resizeRail"
      @toggle="pressGap"
    />
    <AppCardFrame
      tag="main"
      class="ai-window__main"
      data-testid="ai-conversation-card"
    >
      <AppCardHead
        v-if="settingsShown"
        title="Settings"
      />
      <!-- The open chat is named where the eye already is, and renamed from
           the pencil beside the name, as a dashboard is. -->
      <AppCardHead
        v-else-if="selectedChat !== null"
        class="ai-window__head"
        data-testid="ai-chat-head"
      >
        <span
          class="ai-window__head-title"
          :title="selectedChat.title"
          data-testid="ai-chat-heading"
        >{{ selectedChat.title }}</span>
        <AppIconButton
          :icon="appIcons.edit"
          tooltip="Rename this chat"
          data-testid="ai-chat-rename"
          @click="beginRename(selectedChat.id, selectedChat.title)"
        />
      </AppCardHead>
      <AppCardHead
        v-else-if="newDraftOpen"
        :title="draftProject === null ? 'New chat' : `New chat in “${draftProject.name}”`"
        data-testid="ai-draft-head"
      />
      <AppCardHead v-else />
      <AiSettings v-if="settingsShown" />
      <AiConversation
        v-else-if="selected || newDraftOpen"
        :key="selected ?? 'new-agent-chat'"
        :conversation-id="selected"
        :contexts="contexts"
        :project-id="draftProject?.id ?? null"
        @started="startedConversation"
      />
      <div
        v-else
        class="ai-window__welcome"
      >
        <AppButton
          :icon="appIcons.addComment"
          label="New chat"
          @click="makeConversation"
        />
      </div>
    </AppCardFrame>
    <WindowDialog
      v-model="renameShown"
      title="Rename chat"
      size="sm"
      sizing="content"
      data-testid="ai-rename-dialog"
    >
      <AppForm layout="section">
        <AppInput
          ref="renameField"
          v-model="titleDraft"
          label="Name"
          autofocus
          data-testid="ai-rename-input"
          @focus="selectAllIn(renameField)"
          @keydown.enter.prevent="finishRename"
        />
      </AppForm>
      <template #actions>
        <AppButton
          variant="quiet"
          label="Cancel"
          @click="renameShown = false"
        />
        <AppButton
          label="Rename"
          :disable="!titleDraft.trim()"
          data-testid="ai-rename-save"
          @click="finishRename"
        />
      </template>
    </WindowDialog>
    <WindowDialog
      v-model="projectDialogShown"
      :title="renamingProject === null ? 'New project' : 'Rename project'"
      size="sm"
      sizing="stable"
      data-testid="ai-project-dialog"
    >
      <AppForm layout="section">
        <AppInput
          ref="projectField"
          v-model="projectDraft"
          label="Name"
          autofocus
          data-testid="ai-project-name"
          @focus="selectAllIn(projectField)"
          @keyup.enter="saveProject"
        />
      </AppForm>
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
.ai-window__rail { flex-grow: 0; flex-shrink: 0; }
/* Centred rather than padded like a head with a title, as ConnectorRail's. */
.ai-window__rail .ai-window__rail-head { justify-content: center; padding: 0; }
/* At the foot with or without the history above it, so collapsing the rail
   does not lift Settings up under the head. */
.ai-window__rail-foot { flex: none; display: flex; flex-direction: column; align-items: stretch; gap: var(--dp-space-1); margin-top: auto; padding: var(--dp-space-2); border-top: 1px solid var(--dp-border); }
/* The entry says it is the screen being shown, the way a chat row does. */
.ai-window__rail-foot :deep(.q-btn[aria-pressed="true"]) { background: var(--dp-active); }
/* The collapsed rail takes the same forty pixels a collapsed workspace column
   or the dashboards rail does; the wide rail's padding would push past it. */
.ai-window__rail--collapsed .ai-window__rail-foot { align-items: center; padding-right: 0; padding-left: 0; }
.ai-window__history { flex: 1; min-height: 0; overflow: auto; padding: var(--dp-space-1); }
.ai-window__project { display: flex; align-items: center; }
.ai-window__project-name { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--dp-space-1); border: 0; padding: var(--dp-space-1); background: transparent; color: var(--dp-text-muted); font: inherit; font-weight: 600; cursor: pointer; }
.ai-window__project-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-window__project-count { flex: none; color: var(--dp-text-muted); font-weight: 400; }
.ai-window__project-actions { display: none; flex: none; }
.ai-window__project:hover .ai-window__project-actions, .ai-window__project:focus-within .ai-window__project-actions { display: flex; }
/* The chats of a folder are stepped in under its name, which is the whole way
   a reader sees what is in it. */
.ai-window__project-chats { padding-left: var(--dp-space-3); }
.ai-window__group-rule { margin: var(--dp-space-1) var(--dp-space-2); border-top: 1px solid var(--dp-border); }
.ai-window__main { flex: 1; }
.ai-window__filter-head > :first-child { flex: 1; min-width: 0; }
.ai-window__head-title { min-width: 0; overflow: hidden; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.ai-window__welcome { flex: 1; display: grid; place-items: center; }
</style>
