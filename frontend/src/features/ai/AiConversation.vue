<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

import { AiService } from "@/client"
import type { AgentRunPublic, ConversationMessagePublic, ConversationUpdate, ScreenContext } from "@/client"
import { AppBanner, AppButton, AppIconButton, AppInput, AppMenu, AppSelect, AppSpinner, AppTooltip, useToast } from "@/shared/ui"
import type { MenuItem, SelectOption } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { useNow } from "@/shared/freshness/useNow"
import { serverStorageKey } from "@/shared/servers/context"

import ChatMarkdown from "./ChatMarkdown.vue"
import { acceptFor, admit, kindOf } from "./attachments"
import type { AttachmentKind } from "./attachments"
import { useDictation } from "./dictation"
import { useAiDraft } from "./draft"
import { markAt, outlineMarks } from "./outline"
import { unansweredEnds } from "./endedRuns"
import { runDuration } from "./runDuration"
import {
  useAiConversation,
  useAiModels,
  useAiSettings,
  useCreateAiConversation,
  useDeleteAiConversation,
  useAnswerAiRun,
  useCancelAiRun,
  useSendAiMessage,
  useUpdateAiConversation,
  useUpdateAiSettings,
} from "./api"
import AiContextDialog from "./AiContextDialog.vue"
import AiFileChip from "./AiFileChip.vue"
import AiMessageFiles from "./AiMessageFiles.vue"
import AiMessageActions from "./AiMessageActions.vue"
import AiModelSelect from "./AiModelSelect.vue"
import { AUTO_ALL_VALUE, JEV_PROVIDER, autoModelValue, fallbackForAll, fallbackModel, jevProviderLabel, keyedProviders } from "./modelOptions"
import { openQuickChat, quoteSelection } from "./quickChatLauncher"
import { newId } from "@/shared/ids"

const props = defineProps<{
  conversationId: string | null
  contexts: ScreenContext[]
  /** The project a new chat is made in; ignored once the chat exists. */
  projectId?: string | null
}>()
const emit = defineEmits<{ started: [id: string] }>()
const createdId = ref<string | null>(null)
const currentId = computed(() => props.conversationId ?? createdId.value)
const conversation = useAiConversation(currentId)
const settings = useAiSettings()
const models = useAiModels()
const updateConversation = useUpdateAiConversation()
const createConversation = useCreateAiConversation()
const deleteConversation = useDeleteAiConversation()
const updateSettings = useUpdateAiSettings()
const send = useSendAiMessage()
const cancel = useCancelAiRun()
const answer = useAnswerAiRun()
const toast = useToast()
const now = useNow()
const draft = useAiDraft(props.conversationId ?? serverStorageKey("new-agent-chat"))
const contextDialogShown = ref(false)
const selectedContextIds = ref<string[]>([])
const selectedContexts = computed(() => selectedContextIds.value.flatMap((id) => {
  const found = props.contexts.find((context) => context.panel_id === id)
  return found === undefined ? [] : [found]
}))
watch(() => props.contexts.map((context) => context.panel_id), (openIds) => {
  const open = new Set(openIds)
  selectedContextIds.value = selectedContextIds.value.filter((id) => open.has(id))
})
const scroller = ref<HTMLElement | null>(null)
const selectionMenu = ref<{ text: string; left: number; top: number } | null>(null)
const composer = ref<HTMLElement | null>(null)

function selectedMessageText() {
  const selection = window.getSelection()
  const root = scroller.value
  if (!selection || selection.isCollapsed || !root || !selection.anchorNode || !selection.focusNode) {
    selectionMenu.value = null
    return
  }
  const anchor = selection.anchorNode.nodeType === Node.ELEMENT_NODE
    ? selection.anchorNode as Element : selection.anchorNode.parentElement
  const focus = selection.focusNode.nodeType === Node.ELEMENT_NODE
    ? selection.focusNode as Element : selection.focusNode.parentElement
  if (!anchor?.closest(".ai-message__user, .chat-markdown")
    || !focus?.closest(".ai-message__user, .chat-markdown")
    || !root.contains(anchor) || !root.contains(focus)) {
    selectionMenu.value = null
    return
  }
  const text = selection.toString().trim().slice(0, 8000)
  const rect = selection.getRangeAt(0).getBoundingClientRect()
  if (!text || !rect.width) { selectionMenu.value = null; return }
  selectionMenu.value = {
    text,
    left: Math.max(8, Math.min(rect.left, window.innerWidth - 260)),
    top: Math.max(8, rect.top - 42),
  }
}
function onMessagesScroll() {
  trackOutline()
  selectionMenu.value = null
}
function addSelectionToAgent() {
  const text = selectionMenu.value?.text
  if (!text) return
  const quoted = quoteSelection(text)
  draft.value = [draft.value.trimEnd(), quoted].filter(Boolean).join("\n\n") + "\n\n"
  selectionMenu.value = null
  window.getSelection()?.removeAllRanges()
  composer.value?.querySelector("textarea")?.focus()
}
function explainSelection() {
  const text = selectionMenu.value?.text
  if (!text) return
  selectionMenu.value = null
  window.getSelection()?.removeAllRanges()
  openQuickChat({ kind: "explain", text })
}
const expandedSteps = ref(new Set<string>())
const expandedReasoning = ref(new Set<string>())

const runs = computed(() => new Map((conversation.data.value?.runs ?? []).map((run) => [run.id, run])))
const activeRun = computed(() => (conversation.data.value?.runs ?? []).find((run) => ["running", "awaiting_answer"].includes(run.status)) ?? null)
const unrepresentedRuns = computed(() => unansweredEnds(conversation.data.value?.messages ?? [], conversation.data.value?.runs ?? []))

// Files for the next message (D142): kept here until it is sent, each with an
// address of this page to draw or open it from, released when it goes.
interface PendingFile { id: string; file: File; kind: AttachmentKind; address: string }
const pending = ref<PendingFile[]>([])
const picker = ref<HTMLInputElement | null>(null)
const rules = computed(() => settings.data.value?.attachments ?? null)
const currentModel = computed(() => (models.data.value ?? []).find((one) => one.key === fallbackKey.value) ?? null)
const readsImages = computed(() => autoProvider.value
  ? (models.data.value ?? []).some((one) => one.provider === autoProvider.value && one.image_input)
  : currentModel.value?.image_input ?? false)
// An image picked for one model stays when another is chosen; the message
// then waits for a model that reads it, or for the image to go.
const imageProblem = computed(() =>
  readsImages.value ? "" : t("ai.attachments.no_images", { model: currentModel.value?.name ?? t("ai.conversation.this_model") })
)
const blocked = computed(() => pending.value.some((one) => one.kind === "image") && imageProblem.value !== "")
const attachItems = computed<MenuItem[]>(() => [
  {
    name: "tabs",
    label: t("ai.conversation.attach_tabs"),
    icon: appIcons.tab,
    disable: props.contexts.length === 0,
    ...(props.contexts.length === 0 ? { hint: t("ai.conversation.no_tabs") } : {}),
  },
  { name: "files", label: t("ai.conversation.attach_files"), icon: appIcons.attachFile, disable: rules.value === null },
])
function chooseAttachment(name: string) {
  if (name === "tabs") contextDialogShown.value = true
  if (name === "files") picker.value?.click()
}
function pickFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = [...(input.files ?? [])]
  // Emptied, so the same file can be picked again after it was removed.
  input.value = ""
  const given = rules.value
  if (given === null) return
  const { taken, refused } = admit(
    picked,
    pending.value.map((one) => one.file),
    given,
    { name: currentModel.value?.name ?? t("ai.conversation.this_model"), readsImages: readsImages.value }
  )
  pending.value = [...pending.value, ...taken.map((file) => ({
    id: newId(),
    file,
    kind: kindOf(file, given),
    address: URL.createObjectURL(file),
  }))]
  if (refused.length) toast.error(refused.join(". "))
}
function removeFile(id: string) {
  const gone = pending.value.find((one) => one.id === id)
  if (gone) URL.revokeObjectURL(gone.address)
  pending.value = pending.value.filter((one) => one.id !== id)
}
function openFile(address: string) {
  window.open(address, "_blank", "noopener")
}

/**
 * What an empty chat offers to ask, each a thing the agent's tools can answer.
 * Pressed, one is sent as it is written, in the language of the interface.
 */
const EXAMPLES = [
  { key: "connections", icon: appIcons.storage, get text() { return t("ai.conversation.examples.connections") } },
  { key: "about", icon: appIcons.info, get text() { return t("ai.conversation.examples.about") } },
  { key: "tables", icon: appIcons.tableView, get text() { return t("ai.conversation.examples.tables") } },
  { key: "chart", icon: appIcons.insertChart, get text() { return t("ai.conversation.examples.chart") } },
] as const
/**
 * Offered only while the composer is empty: somebody who has started typing is
 * asking their own question, and a press would throw it away.
 */
const examplesShown = computed(() => draft.value.trim() === "" && pending.value.length === 0)
function ask(text: string) {
  draft.value = text
  void submit()
}

const starting = ref(false)
const canSend = computed(() =>
  (draft.value.trim().length > 0 || pending.value.length > 0)
  && !blocked.value
  && activeRun.value === null
  && !send.isPending.value
  && !starting.value
)
// What the agent may do to data from this chat (D136). Read only is the narrow
// end and stands above what the settings allow in general. The fourth choice
// is not this chat's: it is the settings' own switch, offered where changes
// are decided, and it holds in every chat that is not read only.
const EVERY_CHAT = "every"
const pendingPolicy = ref<ConversationUpdate["change_policy"]>("ask")
const pendingModelKey = ref<string | null>(null)
const pendingAutoProvider = ref<ConversationUpdate["auto_provider"]>(null)
const keyed = computed(() => keyedProviders(settings.data.value?.keys ?? []))
const jevKeySet = computed(() => keyed.value.has(JEV_PROVIDER))
const policyOptions = computed<SelectOption[]>(() => [
  { label: t("ai.conversation.policy.read_only"), value: "read_only", icon: appIcons.visibility, description: t("ai.conversation.policy.read_only_hint") },
  { label: t("ai.conversation.policy.ask"), value: "ask", icon: appIcons.helpOutline, description: t("ai.conversation.policy.ask_hint") },
  { label: t("ai.conversation.policy.allow"), value: "allow", icon: appIcons.edit, description: t("ai.conversation.policy.allow_hint") },
  { label: t("ai.conversation.policy.jev"), value: "jev", icon: appIcons.key, description: jevKeySet.value ? t("ai.conversation.policy.jev_hint") : t("ai.conversation.policy.jev_needs_key", { provider: jevProviderLabel }), disable: !jevKeySet.value },
  { label: t("ai.conversation.policy.every"), value: EVERY_CHAT, icon: appIcons.doneAll, description: t("ai.conversation.policy.every_hint"), tone: "warning" },
])
const changePolicy = computed(() => conversation.data.value?.change_policy ?? pendingPolicy.value ?? "ask")
const allowAll = computed(() => settings.data.value?.allow_all_changes ?? false)
const shownPolicy = computed(() =>
  allowAll.value && changePolicy.value !== "read_only" && changePolicy.value !== "jev" ? EVERY_CHAT : changePolicy.value
)
async function choosePolicy(value: unknown) {
  if (typeof value !== "string" || value === shownPolicy.value) return
  if (value === "jev" && !jevKeySet.value) return
  try {
    const id = currentId.value
    if (value === EVERY_CHAT) {
      // Read only would still stand above it here, and this chat is where it
      // was asked for.
      if (changePolicy.value === "read_only") {
        if (id) await updateConversation.mutateAsync({ id, change_policy: "ask" })
        else pendingPolicy.value = "ask"
      }
      await updateSettings.mutateAsync({ allow_all_changes: true })
      return
    }
    if (value !== changePolicy.value) {
      if (id) await updateConversation.mutateAsync({ id, change_policy: value as ConversationUpdate["change_policy"] })
      else pendingPolicy.value = value as ConversationUpdate["change_policy"]
    }
    // Asking, or allowing here alone, cannot hold while every chat is allowed.
    if (value !== "read_only" && value !== "jev" && allowAll.value) {
      await updateSettings.mutateAsync({ allow_all_changes: false })
    }
  }
  catch (cause) { toast.error(messageOf(cause, t("ai.conversation.policy.failed"))) }
}
// What this chat is answered with: its own model, or the one the settings
// chose for every chat that has not said otherwise. Choosing here is also
// choosing for the next chat; the server keeps both (D140).
const fallbackKey = computed(() => conversation.data.value?.model_key ?? pendingModelKey.value ?? settings.data.value?.model_key ?? null)
const autoProvider = computed(() => conversation.data.value?.model_key
  ? conversation.data.value.auto_provider
  : pendingModelKey.value ? pendingAutoProvider.value : settings.data.value?.auto_provider)
const chatModel = computed(() => autoProvider.value ? autoModelValue(autoProvider.value) : fallbackKey.value)
async function chooseModel(value: string) {
  if (value === chatModel.value) return
  if (value === AUTO_ALL_VALUE) {
    const fallback = fallbackForAll(models.data.value ?? [], fallbackKey.value, keyed.value)
    if (!fallback) return
    try {
      const id = currentId.value
      if (id) await updateConversation.mutateAsync({ id, model_key: fallback.key, auto_provider: "all" })
      else {
        pendingModelKey.value = fallback.key
        pendingAutoProvider.value = "all"
        await updateSettings.mutateAsync({ model_key: fallback.key, auto_provider: "all" })
      }
    }
    catch (cause) { toast.error(messageOf(cause, t("ai.composer.model_failed"))) }
    return
  }
  const provider = models.data.value?.find((one) => value === autoModelValue(one.provider))?.provider
  const fallback = provider ? fallbackModel(models.data.value ?? [], fallbackKey.value, provider) : null
  if (provider && !fallback) return
  try {
    const id = currentId.value
    if (id) await updateConversation.mutateAsync({ id, model_key: fallback?.key ?? value, auto_provider: provider ?? null })
    else {
      pendingModelKey.value = fallback?.key ?? value
      pendingAutoProvider.value = provider ?? null
      // No conversation yet to keep it: the settings keep the last model
      // picked anywhere (D140), so a reload still opens on it.
      await updateSettings.mutateAsync({ model_key: fallback?.key ?? value, auto_provider: provider ?? null })
    }
  }
  catch (cause) { toast.error(messageOf(cause, t("ai.composer.model_failed"))) }
}

// The contents of the conversation, down the edge of it: one mark per
// question, and the one being read is the last one above the top of the view.
const marks = computed(() => outlineMarks(conversation.data.value?.messages ?? []))
const currentMark = ref<string | null>(null)
function messageElement(id: string): HTMLElement | null {
  return scroller.value?.querySelector<HTMLElement>(`[data-message="${id}"]`) ?? null
}
function trackOutline() {
  const root = scroller.value
  if (root === null) return
  const offsets = marks.value.flatMap((mark) => {
    const element = messageElement(mark.id)
    return element === null ? [] : [{ id: mark.id, top: element.offsetTop }]
  })
  currentMark.value = markAt(offsets, root.scrollTop)
}
function goToMark(id: string) {
  const root = scroller.value
  const target = messageElement(id)
  if (root === null || target === null) return
  root.scrollTo({ top: Math.max(0, target.offsetTop - 8), behavior: "smooth" })
  currentMark.value = id
}

function runFor(message: ConversationMessagePublic): AgentRunPublic | undefined {
  return message.run_id ? runs.value.get(message.run_id) : undefined
}
/** A failed run's sentence, shown with the answer it managed — a run that
 * streamed half an answer before failing is represented by that message and
 * never reaches the banners below, so without this nothing says it failed. */
function errorOf(message: ConversationMessagePublic): string | null {
  const run = runFor(message)
  if (run === undefined || run.status !== "failed") return null
  return run.error ?? t("ai.conversation.answer_failed")
}
function stepSummary(run: AgentRunPublic): string {
  const model = models.data.value?.find((one) => one.key === run.model_key)?.name ?? run.model_key
  const duration = runDuration(run, now.value)
  const steps = run.steps ?? []
  const current = [...steps].reverse().find((step) => step.status === "running")
  if (current) return `${model} · ${current.title} · ${duration}`
  return `${model} · ${t("ai.conversation.steps", { n: steps.length }, steps.length)}${duration ? ` · ${duration}` : ""}`
}
function toggle(set: Set<string>, id: string) {
  const next = new Set(set)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  if (set === expandedSteps.value) expandedSteps.value = next
  else expandedReasoning.value = next
}
async function submit() {
  const text = draft.value.trim()
  if (!canSend.value) return
  starting.value = true
  dictation.stop()
  let id = currentId.value
  let madeHere = false
  try {
    if (id === null) {
      id = (await createConversation.mutateAsync()).id
      createdId.value = id
      madeHere = true
      await updateConversation.mutateAsync({
        id,
        change_policy: pendingPolicy.value,
        ...(props.projectId ? { project_id: props.projectId } : {}),
        ...(pendingModelKey.value ? { model_key: pendingModelKey.value, auto_provider: pendingAutoProvider.value } : {}),
      })
    }
    await send.mutateAsync({
      id,
      text,
      contexts: selectedContexts.value,
      files: pending.value.map((one) => one.file),
    })
    draft.value = ""
    if (props.conversationId === null) emit("started", id)
    selectedContextIds.value = []
    for (const one of pending.value) URL.revokeObjectURL(one.address)
    pending.value = []
  }
  catch (cause) {
    if (props.conversationId === null && id !== null) {
      try {
        const saved = (await AiService.readConversation({ path: { conversation_id: id } })).data
        if (saved.messages.length || saved.runs.length) {
          draft.value = ""
          emit("started", id)
        } else {
          if (madeHere || createdId.value === id) {
            await deleteConversation.mutateAsync(id)
            createdId.value = null
          }
        }
      } catch { /* Retain the chat ID until its saved state can be checked. */ }
    }
    toast.error(messageOf(cause, t("ai.conversation.send_failed")))
  } finally { starting.value = false }
}
function onEditorKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.shiftKey) return
  event.preventDefault()
  void submit()
}
async function stop() {
  if (!activeRun.value || !currentId.value) return
  try { await cancel.mutateAsync({ id: activeRun.value.id, conversationId: currentId.value }) }
  catch (cause) { toast.error(messageOf(cause, t("ai.composer.stop_failed"))) }
}
async function answerQuestion(choice: string) {
  if (!activeRun.value?.question || !currentId.value) return
  try {
    await answer.mutateAsync({
      id: activeRun.value.id,
      conversationId: currentId.value,
      answer: choice,
    })
  }
  catch (cause) { toast.error(messageOf(cause, t("ai.conversation.continue_failed"))) }
}
// What was typed before the microphone was pressed. Everything heard is kept
// beside it, so speaking adds to a half-written message instead of erasing it.
const spokenInto = ref("")
const dictation = useDictation(
  (heard) => { draft.value = `${spokenInto.value}${heard}` },
  (reason) => {
    toast.error(reason === "not-allowed"
      ? t("ai.composer.mic_refused")
      : t("ai.composer.dictation_stopped"))
  }
)
/** What a run that ended without an answer says, when it gave no reason. */
function endedWords(run: AgentRunPublic): string {
  if (run.status === "cancelled") return t("ai.conversation.ended.cancelled")
  if (run.status === "interrupted") return t("ai.conversation.ended.interrupted")
  return t("ai.conversation.ended.failed")
}
function dictate() {
  if (!dictation.listening.value) {
    const typed = draft.value.trimEnd()
    spokenInto.value = typed ? `${typed} ` : ""
  }
  dictation.toggle()
}

watch(() => conversation.data.value, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  trackOutline()
}, { deep: true })
onBeforeUnmount(() => {
  dictation.stop()
  for (const one of pending.value) URL.revokeObjectURL(one.address)
})
</script>

<template>
  <div class="ai-conversation">
    <AppSpinner v-if="currentId !== null && conversation.isPending.value" />
    <AppBanner
      v-else-if="conversation.isError.value"
      tone="error"
    >
      {{ t('ai.conversation.load_failed') }}
    </AppBanner>
    <template v-else>
      <div class="ai-conversation__body">
        <nav
          v-if="marks.length > 1"
          class="ai-outline"
          :aria-label="t('ai.outline.label')"
          data-testid="ai-outline"
        >
          <button
            v-for="mark in marks"
            :key="mark.id"
            type="button"
            class="ai-outline__mark"
            :class="{ 'ai-outline__mark--current': mark.id === currentMark }"
            :aria-label="mark.label"
            :data-testid="`ai-outline-${mark.id}`"
            @click="goToMark(mark.id)"
          >
            <AppTooltip beside>
              {{ mark.label }}
            </AppTooltip>
          </button>
        </nav>
        <div
          ref="scroller"
          class="ai-conversation__messages"
          data-testid="ai-messages"
          @scroll="onMessagesScroll"
        >
          <div
            class="ai-conversation__transcript"
            @pointerup="selectedMessageText"
            @keyup="selectedMessageText"
          >
            <div
              v-if="!conversation.data.value?.messages.length && !activeRun"
              class="ai-conversation__empty"
            >
              <q-icon
                :name="appIcons.autoAwesome"
                size="var(--dp-icon-xl)"
              />
              <div
                v-if="examplesShown"
                class="ai-conversation__examples"
                data-testid="ai-examples"
              >
                <AppButton
                  v-for="example in EXAMPLES"
                  :key="example.key"
                  variant="quiet"
                  layout="navigation"
                  :icon="example.icon"
                  :label="example.text"
                  :disable="starting || send.isPending.value"
                  class="ai-conversation__example"
                  @click="ask(example.text)"
                />
              </div>
              <span v-else>{{ t('ai.composer.empty') }}</span>
            </div>
            <article
              v-for="message in conversation.data.value?.messages ?? []"
              :key="message.id"
              class="ai-message"
              :class="`ai-message--${message.role}`"
              :data-message="message.id"
            >
              <div
                v-if="message.role === 'assistant' && runFor(message)"
                class="ai-steps"
              >
                <button
                  type="button"
                  class="ai-steps__summary"
                  :aria-expanded="expandedSteps.has(runFor(message)!.id)"
                  @click="toggle(expandedSteps, runFor(message)!.id)"
                >
                  <q-icon :name="expandedSteps.has(runFor(message)!.id) ? 'keyboard_arrow_down' : 'chevron_right'" />
                  {{ stepSummary(runFor(message)!) }}
                </button>
                <div
                  v-if="expandedSteps.has(runFor(message)!.id)"
                  class="ai-steps__list"
                >
                  <div
                    v-for="step in runFor(message)!.steps ?? []"
                    :key="step.ordinal"
                    class="ai-step"
                  >
                    <span>{{ step.title }}</span><span>{{ t(`ai.conversation.step_status.${step.status}`) }}</span>
                    <button
                      v-if="step.kind === 'thinking' && step.detail"
                      type="button"
                      class="ai-step__reasoning"
                      @click="toggle(expandedReasoning, `${runFor(message)!.id}:${String(step.ordinal)}`)"
                    >
                      {{ t('ai.conversation.thinking') }}
                    </button>
                    <div
                      v-if="step.kind === 'thinking' && step.detail && expandedReasoning.has(`${runFor(message)!.id}:${String(step.ordinal)}`)"
                      class="ai-step__detail"
                    >
                      {{ step.detail }}
                    </div>
                    <div
                      v-for="(substep, index) in step.substeps ?? []"
                      :key="`${String(index)}:${substep}`"
                      class="ai-step__detail"
                    >
                      {{ substep }}
                    </div>
                  </div>
                </div>
              </div>
              <AiMessageFiles
                v-if="message.role === 'user' && message.attachments?.length"
                :conversation-id="currentId ?? ''"
                :files="message.attachments"
              />
              <div
                v-if="message.role === 'user' && message.content"
                class="ai-message__user"
              >
                {{ message.content }}
              </div>
              <ChatMarkdown
                v-else-if="message.role !== 'user'"
                :text="message.content"
              />
              <AppBanner
                v-if="message.role === 'assistant' && errorOf(message)"
                tone="warning"
                class="ai-message__error"
                data-testid="ai-message-error"
              >
                {{ errorOf(message) }}
              </AppBanner>
              <AiMessageActions
                class="ai-message__actions"
                :text="message.content"
                :role="message.role"
              />
            </article>
            <article
              v-if="activeRun"
              class="ai-message ai-message--assistant"
              data-testid="ai-streaming-answer"
            >
              <div class="ai-steps">
                <button
                  type="button"
                  class="ai-steps__summary"
                  :aria-expanded="expandedSteps.has(activeRun.id)"
                  @click="toggle(expandedSteps, activeRun.id)"
                >
                  <q-icon :name="expandedSteps.has(activeRun.id) ? 'keyboard_arrow_down' : 'chevron_right'" />{{ stepSummary(activeRun) }}
                </button>
                <div
                  v-if="expandedSteps.has(activeRun.id)"
                  class="ai-steps__list"
                >
                  <div
                    v-for="step in activeRun.steps ?? []"
                    :key="step.ordinal"
                    class="ai-step"
                  >
                    <span>{{ step.title }}</span><span>{{ t(`ai.conversation.step_status.${step.status}`) }}</span>
                    <button
                      v-if="step.kind === 'thinking' && step.detail"
                      type="button"
                      class="ai-step__reasoning"
                      @click="toggle(expandedReasoning, `${activeRun.id}:${String(step.ordinal)}`)"
                    >
                      {{ t('ai.conversation.thinking') }}
                    </button>
                    <div
                      v-if="step.kind === 'thinking' && step.detail && expandedReasoning.has(`${activeRun.id}:${String(step.ordinal)}`)"
                      class="ai-step__detail"
                    >
                      {{ step.detail }}
                    </div>
                    <div
                      v-for="(substep, index) in step.substeps ?? []"
                      :key="`${String(index)}:${substep}`"
                      class="ai-step__detail"
                    >
                      {{ substep }}
                    </div>
                  </div>
                </div>
              </div>
              <ChatMarkdown
                v-if="activeRun.partial_answer"
                :text="activeRun.partial_answer"
              />
              <div
                v-if="activeRun.question"
                class="ai-question"
                data-testid="ai-question"
              >
                <div>{{ activeRun.question.question }}</div>
                <div
                  v-if="activeRun.question.kind === 'confirm_change' && activeRun.question.preview"
                  class="ai-question__preview"
                  data-testid="ai-question-preview"
                >
                  <div class="ai-question__preview-summary">
                    {{ activeRun.question.preview.summary }}
                  </div>
                  <div
                    v-for="(line, index) in activeRun.question.preview.lines ?? []"
                    :key="`${String(index)}:${line}`"
                    class="ai-question__preview-line"
                  >
                    {{ line }}
                  </div>
                </div>
                <div class="ai-question__choices">
                  <AppButton
                    v-for="choice in activeRun.question.choices"
                    :key="choice"
                    :label="choice"
                    :disable="answer.isPending.value"
                    @click="answerQuestion(choice)"
                  />
                </div>
              </div>
            </article>
            <AppBanner
              v-for="run in unrepresentedRuns"
              :key="run.id"
              :tone="run.status === 'cancelled' ? 'info' : 'warning'"
              data-testid="ai-run-ended"
            >
              {{ run.error || endedWords(run) }}
            </AppBanner>
          </div>
          <div class="ai-conversation__dock">
            <div
              ref="composer"
              class="ai-conversation__composer"
              data-testid="ai-composer"
            >
              <div
                v-if="selectedContexts.length"
                class="ai-conversation__contexts"
                :aria-label="t('ai.conversation.contexts')"
              >
                <span
                  v-for="context in selectedContexts"
                  :key="context.panel_id"
                  class="ai-context-chip"
                >
                  <span class="ai-context-chip__label">{{ context.label }}</span>
                  <AppIconButton
                    :icon="appIcons.close"
                    :tooltip="t('ai.common.remove', { name: context.label })"
                    compact
                    @click="selectedContextIds = selectedContextIds.filter((id) => id !== context.panel_id)"
                  />
                </span>
              </div>
              <div
                v-if="pending.length"
                class="ai-conversation__contexts"
                :aria-label="t('ai.conversation.files')"
              >
                <AiFileChip
                  v-for="one in pending"
                  :key="one.id"
                  :name="one.file.name"
                  :size="one.file.size"
                  :kind="one.kind"
                  :thumbnail="one.address"
                  :problem="one.kind === 'image' ? imageProblem : ''"
                  removable
                  @open="openFile(one.address)"
                  @remove="removeFile(one.id)"
                />
              </div>
              <AppInput
                v-model="draft"
                type="textarea"
                grow
                compact
                :placeholder="t('ai.conversation.placeholder')"
                :aria-label="t('ai.conversation.placeholder')"
                data-testid="ai-message-input"
                :disable="activeRun !== null"
                @keydown="onEditorKeydown"
              />
              <!-- What the next message is sent with, under the message itself. -->
              <div class="ai-conversation__tools">
                <!-- The menu hangs off the span: the button alone would give it no
                     element to open from while it is disabled. -->
                <span>
                  <AppIconButton
                    :icon="appIcons.add"
                    :tooltip="t('ai.conversation.attach')"
                    data-testid="ai-attach"
                    :disable="activeRun !== null"
                  />
                  <AppMenu
                    v-if="activeRun === null"
                    :items="attachItems"
                    @select="chooseAttachment"
                  />
                </span>
                <input
                  ref="picker"
                  type="file"
                  multiple
                  class="ai-conversation__picker"
                  :accept="rules ? acceptFor(rules, readsImages) : undefined"
                  data-testid="ai-file-input"
                  @change="pickFiles"
                >
                <AppSelect
                  class="ai-conversation__policy"
                  compact
                  :model-value="shownPolicy"
                  :options="policyOptions"
                  :disable="activeRun !== null"
                  :label="t('ai.conversation.policy.label')"
                  label-hidden
                  framed
                  data-testid="ai-chat-policy"
                  @update:model-value="choosePolicy"
                />
                <AiModelSelect
                  class="ai-conversation__model"
                  compact
                  :model-value="chatModel"
                  :pending="currentId !== null && conversation.isPending.value"
                  :disable="activeRun !== null"
                  data-testid="ai-chat-model"
                  @update:model-value="chooseModel"
                />
                <AppIconButton
                  :icon="dictation.listening.value ? appIcons.mic : appIcons.micNone"
                  :live="dictation.listening.value"
                  :tooltip="!dictation.supported
                    ? t('ai.composer.cannot_listen')
                    : dictation.listening.value ? t('ai.composer.stop_dictating') : t('ai.composer.dictate')"
                  :disable="!dictation.supported || activeRun !== null"
                  data-testid="ai-dictate"
                  @click="dictate"
                />
                <span class="ai-conversation__gap" />
                <AppButton
                  v-if="activeRun"
                  variant="danger-quiet"
                  :icon="appIcons.stop"
                  :label="t('ai.composer.stop')"
                  :loading="cancel.isPending.value"
                  data-testid="ai-stop"
                  @click="stop"
                />
                <AppButton
                  v-else
                  :icon="appIcons.send"
                  :label="t('ai.composer.send')"
                  icon-only
                  class="ai-conversation__send"
                  :disable="!canSend"
                  data-testid="ai-send"
                  @click="submit"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
      <div
        v-if="selectionMenu"
        class="ai-selection-menu"
        :style="{ left: `${selectionMenu.left}px`, top: `${selectionMenu.top}px` }"
        data-testid="ai-selection-menu"
        @pointerdown.prevent
      >
        <AppButton
          variant="quiet"
          size="sm"
          :label="t('ai.conversation.add_to_chat')"
          @click="addSelectionToAgent"
        />
        <AppButton
          variant="quiet"
          size="sm"
          :label="t('ai.conversation.more_details')"
          @click="explainSelection"
        />
      </div>
      <AiContextDialog
        v-model="contextDialogShown"
        :contexts="contexts"
        :selected="selectedContextIds"
        @apply="selectedContextIds = $event"
      />
    </template>
  </div>
</template>

<style scoped>
.ai-conversation { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.ai-selection-menu { position: fixed; z-index: var(--dp-layer-popover); display: flex; gap: var(--dp-space-1); padding: var(--dp-space-1); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface-raised); box-shadow: 0 8px 24px var(--dp-shadow-soft); }
.ai-conversation__body { flex: 1; min-height: 0; display: flex; }
/* The messages hold the marks' coordinates: offsetTop is measured against this
   box, so it has to be the one they are positioned in. It holds the composer
   too and runs to the foot of the card, so the transcript scrolls the whole
   height and passes under the composer instead of stopping above it. */
.ai-conversation__messages { position: relative; flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }
/* Grown to the room above the composer, so an empty chat is centred there.
   A stacking context of its own, so nothing raised inside an answer is
   painted over the composer it passes under. */
.ai-conversation__transcript { flex: 1 0 auto; padding: var(--dp-space-5) var(--dp-space-4) 0; isolation: isolate; }
.ai-conversation__transcript > .ai-message, .ai-conversation__transcript > .app-banner { max-width: var(--dp-page-max-width); margin-left: auto; margin-right: auto; }
.ai-outline { flex: none; display: flex; flex-direction: column; justify-content: center; gap: var(--dp-space-1); padding: var(--dp-space-2) var(--dp-space-1); overflow: hidden; }
/* The mark is two pixels of ink in a target a finger can hit. */
.ai-outline__mark { display: grid; place-items: center; width: 20px; height: 12px; border: 0; padding: 0; background: transparent; cursor: pointer; }
.ai-outline__mark::before { content: ""; width: 12px; height: 2px; border-radius: 1px; background: var(--dp-border-strong); transition: width 120ms ease, background-color 120ms ease; }
.ai-outline__mark:hover::before { background: var(--dp-text-muted); }
.ai-outline__mark--current::before { width: 16px; background: var(--dp-text); }
/* A floor and not a height: in a card shorter than the examples a height
   cut their top off where no scroll could reach it. */
.ai-conversation__empty { min-height: 100%; display: grid; place-content: center; justify-items: center; gap: var(--dp-space-2); color: var(--dp-text-muted); }
.ai-conversation__examples { max-width: 100%; display: flex; flex-direction: column; gap: var(--dp-space-2); }
.ai-conversation__example { border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); }
.ai-message { margin: 0 0 var(--dp-space-4); }
.ai-message--user { display: flex; flex-direction: column; align-items: flex-end; }
.ai-message__user { max-width: 78%; padding: var(--dp-space-2) var(--dp-space-3); font-size: var(--dp-prose-font-size); line-height: var(--dp-prose-line-height); white-space: pre-wrap; background: var(--dp-active); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); }
.ai-message__actions { display: flex; gap: var(--dp-space-1); margin-top: var(--dp-space-1); opacity: 0; pointer-events: none; transition: opacity 120ms ease; }
.ai-message:hover .ai-message__actions, .ai-message:focus-within .ai-message__actions { opacity: 1; pointer-events: auto; }
@media (hover: none) { .ai-message__actions { opacity: 1; pointer-events: auto; } }
.ai-message__error { margin-top: var(--dp-space-2); }
.ai-steps { margin-bottom: var(--dp-space-3); color: var(--dp-text-muted); font-size: inherit; line-height: var(--dp-prose-line-height); }
.ai-steps__summary, .ai-step__reasoning { border: 0; padding: 0; background: transparent; color: inherit; cursor: pointer; }
.ai-steps__summary { display: flex; align-items: center; gap: var(--dp-space-1); font-size: inherit; }
.ai-steps__list { margin: var(--dp-space-1) 0 0 var(--dp-space-4); }
.ai-step { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--dp-space-1) var(--dp-space-3); padding: var(--dp-space-1) 0; }
.ai-step__reasoning { grid-column: 1 / -1; width: fit-content; font-size: inherit; text-decoration: underline; }
.ai-step__detail { grid-column: 1 / -1; overflow-wrap: anywhere; white-space: pre-wrap; color: var(--dp-text-muted); }
.ai-question { display: grid; gap: var(--dp-space-2); padding: var(--dp-space-3); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface); }
.ai-question__choices { display: flex; flex-wrap: wrap; gap: var(--dp-space-2); }
.ai-question__preview { display: grid; gap: var(--dp-space-1); padding: var(--dp-space-2) 0 0; font-size: var(--dp-font-size-sm); color: var(--dp-text-muted); }
.ai-question__preview-summary { color: var(--dp-text); }
.ai-question__preview-line { white-space: pre-wrap; }
/* Held at the foot of the scroller while the transcript moves under it, and
   left where it lies at the end of it, so the last message stops above the
   composer. The card's ground fills in round the composer, so text passing
   under it does not show in the gaps. */
.ai-conversation__dock { position: sticky; bottom: 0; flex: none; padding: var(--dp-space-2) var(--dp-space-4) var(--dp-space-3); background: linear-gradient(transparent, var(--dp-surface) var(--dp-space-2)); }
.ai-conversation__composer { box-sizing: border-box; display: flex; flex-direction: column; gap: var(--dp-space-2); width: 100%; max-width: var(--dp-page-max-width); margin: 0 auto; padding: var(--dp-space-3); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface-raised); box-shadow: 0 8px 24px var(--dp-shadow-soft); }
.ai-conversation__contexts { display: flex; flex-wrap: wrap; gap: var(--dp-space-1); }
.ai-conversation__picker { display: none; }
/* One row: the two choices give way before anything wraps. Wrapped, at 1024px the microphone went down a line on its own. */
.ai-conversation__tools { display: flex; align-items: center; gap: var(--dp-space-2); }
.ai-conversation__composer :deep(.q-field:not(.app-select--framed) .q-field__control) { background: transparent; }
.ai-conversation__composer :deep(.q-field:not(.app-select--framed) .q-field__control::before) { border-color: transparent; }
.ai-conversation__composer :deep(.q-field--focused .q-field__control::after) { border-color: var(--dp-field-border); }
.ai-conversation__send { border-radius: var(--dp-radius-control); }
.ai-conversation__gap { flex: 1; }
/* Wide enough for a model's name and no wider: the row it stands in belongs
   to the send button at its end. */
/* Wide enough for the name beside the value as well as the value. */
.ai-conversation__model, .ai-conversation__policy { flex: 0 1 260px; min-width: 120px; }
.ai-conversation__policy { flex-basis: 304px; }
.ai-context-chip { display: inline-flex; align-items: center; max-width: 100%; gap: var(--dp-space-1); padding-left: var(--dp-space-2); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-control); background: var(--dp-surface); color: var(--dp-text); }
.ai-context-chip__label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* The box is one line until there is more to hold, and stops at eight of them
   rather than pushing the transcript off the card. A grown field scrolls; the
   corner grip is gone with it, because a hand-dragged height had no floor and
   no ceiling and was forgotten on every chat switch. */
.ai-conversation__composer :deep(textarea) { max-height: 8lh; }
</style>
