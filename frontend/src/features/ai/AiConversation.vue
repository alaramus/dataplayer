<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

import type { AgentRunPublic, ConversationMessagePublic, ConversationUpdate, ScreenContext } from "@/client"
import { AppBanner, AppButton, AppIconButton, AppInput, AppSelect, AppSpinner, useToast } from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import ChatMarkdown from "./ChatMarkdown.vue"
import { useDictation } from "./dictation"
import { markAt, outlineMarks } from "./outline"
import { plainSpeechText } from "./streaming"
import {
  useAiConversation,
  useAiSettings,
  useAnswerAiRun,
  useCancelAiRun,
  useSendAiMessage,
  useUpdateAiConversation,
  useUpdateAiSettings,
} from "./api"
import AiContextDialog from "./AiContextDialog.vue"
import AiModelSelect from "./AiModelSelect.vue"

const props = defineProps<{ conversationId: string; contexts: ScreenContext[] }>()
const conversation = useAiConversation(() => props.conversationId)
const settings = useAiSettings()
const updateConversation = useUpdateAiConversation()
const updateSettings = useUpdateAiSettings()
const send = useSendAiMessage()
const cancel = useCancelAiRun()
const answer = useAnswerAiRun()
const toast = useToast()
const draft = ref("")
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
const expandedSteps = ref(new Set<string>())
const expandedReasoning = ref(new Set<string>())
let speech: SpeechSynthesisUtterance | null = null

const runs = computed(() => new Map((conversation.data.value?.runs ?? []).map((run) => [run.id, run])))
const activeRun = computed(() => (conversation.data.value?.runs ?? []).find((run) => ["running", "awaiting_answer"].includes(run.status)) ?? null)
const unrepresentedRuns = computed(() => {
  const represented = new Set((conversation.data.value?.messages ?? []).flatMap((message) => message.run_id ? [message.run_id] : []))
  return (conversation.data.value?.runs ?? []).filter((run) => !represented.has(run.id) && !["running", "awaiting_answer", "succeeded"].includes(run.status))
})
const canSend = computed(() => draft.value.trim().length > 0 && activeRun.value === null && !send.isPending.value)
// What the agent may do to data from this chat (D136). Read only is the narrow
// end and stands above what the settings allow in general. The fourth choice
// is not this chat's: it is the settings' own switch, offered where changes
// are decided, and it holds in every chat that is not read only.
const EVERY_CHAT = "every"
const policyOptions: SelectOption[] = [
  { label: "Read only", value: "read_only", icon: "visibility", description: "Nothing is changed from this chat" },
  { label: "Ask before changes", value: "ask", icon: "help_outline", description: "Every change is confirmed first" },
  { label: "Allow changes", value: "allow", icon: "edit", description: "Changes in this chat run without asking" },
  { label: "Allow all changes in every chat", value: EVERY_CHAT, icon: "done_all", description: "Changes in every chat run without asking", tone: "warning" },
]
const changePolicy = computed(() => conversation.data.value?.change_policy ?? "ask")
const allowAll = computed(() => settings.data.value?.allow_all_changes ?? false)
const shownPolicy = computed(() =>
  allowAll.value && changePolicy.value !== "read_only" ? EVERY_CHAT : changePolicy.value
)
async function choosePolicy(value: unknown) {
  if (typeof value !== "string" || value === shownPolicy.value) return
  try {
    if (value === EVERY_CHAT) {
      // Read only would still stand above it here, and this chat is where it
      // was asked for.
      if (changePolicy.value === "read_only") await updateConversation.mutateAsync({ id: props.conversationId, change_policy: "ask" })
      await updateSettings.mutateAsync({ allow_all_changes: true })
      return
    }
    if (value !== changePolicy.value) await updateConversation.mutateAsync({ id: props.conversationId, change_policy: value as ConversationUpdate["change_policy"] })
    // Asking, or allowing here alone, cannot hold while every chat is allowed.
    if (value !== "read_only" && allowAll.value) await updateSettings.mutateAsync({ allow_all_changes: false })
  }
  catch (cause) { toast.error(messageOf(cause, "The permission could not be changed")) }
}
// What this chat is answered with: its own model, or the one the settings
// chose for every chat that has not said otherwise.
const chatModel = computed(() => conversation.data.value?.model_key ?? settings.data.value?.model_key ?? null)
async function chooseModel(value: string) {
  if (value === chatModel.value) return
  try { await updateConversation.mutateAsync({ id: props.conversationId, model_key: value }) }
  catch (cause) { toast.error(messageOf(cause, "The model could not be chosen")) }
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
  return run.error ?? "The answer failed."
}
function duration(run: AgentRunPublic): string {
  if (!run.created_at) return ""
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now()
  const seconds = Math.max(0, Math.round((end - new Date(run.created_at).getTime()) / 1000))
  return `${String(seconds)} s`
}
function stepSummary(run: AgentRunPublic): string {
  const steps = run.steps ?? []
  const current = [...steps].reverse().find((step) => step.status === "running")
  if (current) return `${current.title} · ${duration(run)}`
  return `${String(steps.length)} ${steps.length === 1 ? "step" : "steps"}${duration(run) ? ` · ${duration(run)}` : ""}`
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
  draft.value = ""
  dictation.stop()
  try {
    await send.mutateAsync({ id: props.conversationId, text, contexts: selectedContexts.value })
    selectedContextIds.value = []
  }
  catch (cause) { draft.value = text; toast.error(messageOf(cause, "The message could not be sent")) }
}
function onEditorKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.shiftKey) return
  event.preventDefault()
  void submit()
}
async function stop() {
  if (!activeRun.value) return
  try { await cancel.mutateAsync({ id: activeRun.value.id, conversationId: props.conversationId }) }
  catch (cause) { toast.error(messageOf(cause, "The answer could not be stopped")) }
}
async function answerQuestion(choice: string) {
  if (!activeRun.value?.question) return
  try {
    await answer.mutateAsync({
      id: activeRun.value.id,
      conversationId: props.conversationId,
      answer: choice,
    })
  }
  catch (cause) { toast.error(messageOf(cause, "The answer could not be continued")) }
}
// What was typed before the microphone was pressed. Everything heard is kept
// beside it, so speaking adds to a half-written message instead of erasing it.
const spokenInto = ref("")
const dictation = useDictation(
  (heard) => { draft.value = `${spokenInto.value}${heard}` },
  (reason) => {
    toast.error(reason === "not-allowed"
      ? "The microphone is not allowed for this page"
      : "Dictation stopped")
  }
)
function dictate() {
  if (!dictation.listening.value) {
    const typed = draft.value.trimEnd()
    spokenInto.value = typed ? `${typed} ` : ""
  }
  dictation.toggle()
}
async function copy(text: string, what: string) {
  try { await navigator.clipboard.writeText(text); toast.success(`${what} copied`) }
  catch { toast.error(`The ${what.toLowerCase()} could not be copied`) }
}
function listen(text: string) {
  window.speechSynthesis.cancel()
  const plain = plainSpeechText(text)
  if (!plain) return
  speech = new SpeechSynthesisUtterance(plain)
  window.speechSynthesis.speak(speech)
}

watch(() => conversation.data.value, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  trackOutline()
}, { deep: true })
onBeforeUnmount(() => {
  if (speech) window.speechSynthesis.cancel()
  dictation.stop()
})
</script>

<template>
  <div class="ai-conversation">
    <AppSpinner v-if="conversation.isPending.value" />
    <AppBanner
      v-else-if="conversation.isError.value"
      tone="error"
    >
      This conversation could not be loaded.
    </AppBanner>
    <template v-else>
      <div class="ai-conversation__body">
        <nav
          v-if="marks.length > 1"
          class="ai-outline"
          aria-label="What was asked in this chat"
          data-testid="ai-outline"
        >
          <button
            v-for="mark in marks"
            :key="mark.id"
            type="button"
            class="ai-outline__mark"
            :class="{ 'ai-outline__mark--current': mark.id === currentMark }"
            :title="mark.label"
            :aria-label="mark.label"
            :data-testid="`ai-outline-${mark.id}`"
            @click="goToMark(mark.id)"
          />
        </nav>
        <div
          ref="scroller"
          class="ai-conversation__messages"
          data-testid="ai-messages"
          @scroll="trackOutline"
        >
          <div
            v-if="!conversation.data.value?.messages.length && !activeRun"
            class="ai-conversation__empty"
          >
            <q-icon
              name="auto_awesome"
              size="32px"
            />
            <span>What would you like to know?</span>
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
                <q-icon :name="expandedSteps.has(runFor(message)!.id) ? 'expand_more' : 'chevron_right'" />
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
                  <span>{{ step.title }}</span><span>{{ step.status }}</span>
                  <button
                    v-if="step.kind === 'thinking' && step.detail"
                    type="button"
                    class="ai-step__reasoning"
                    @click="toggle(expandedReasoning, `${runFor(message)!.id}:${String(step.ordinal)}`)"
                  >
                    Thinking
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
            <div
              v-if="message.role === 'user'"
              class="ai-message__user"
            >
              {{ message.content }}
            </div>
            <ChatMarkdown
              v-else
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
            <div
              class="ai-message__actions"
            >
              <AppIconButton
                icon="content_copy"
                :tooltip="message.role === 'user' ? 'Copy message' : 'Copy answer'"
                @click="copy(message.content, message.role === 'user' ? 'Message' : 'Answer')"
              />
              <AppIconButton
                icon="volume_up"
                :tooltip="message.role === 'user' ? 'Listen to message' : 'Listen to answer'"
                @click="listen(message.content)"
              />
            </div>
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
                <q-icon :name="expandedSteps.has(activeRun.id) ? 'expand_more' : 'chevron_right'" />{{ stepSummary(activeRun) }}
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
                  <span>{{ step.title }}</span><span>{{ step.status }}</span>
                  <button
                    v-if="step.kind === 'thinking' && step.detail"
                    type="button"
                    class="ai-step__reasoning"
                    @click="toggle(expandedReasoning, `${activeRun.id}:${String(step.ordinal)}`)"
                  >
                    Thinking
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
            {{ run.error || (run.status === "cancelled" ? "The answer was stopped." : `The answer was ${run.status}.`) }}
          </AppBanner>
        </div>
      </div>
      <div class="ai-conversation__composer">
        <div
          v-if="selectedContexts.length"
          class="ai-conversation__contexts"
          aria-label="Tabs attached to the next message"
        >
          <span
            v-for="context in selectedContexts"
            :key="context.panel_id"
            class="ai-context-chip"
          >
            {{ context.label }}
            <AppIconButton
              icon="close"
              :tooltip="`Remove ${context.label}`"
              compact
              @click="selectedContextIds = selectedContextIds.filter((id) => id !== context.panel_id)"
            />
          </span>
        </div>
        <AppInput
          v-model="draft"
          type="textarea"
          grow
          compact
          placeholder="Message the agent"
          aria-label="Message the agent"
          data-testid="ai-message-input"
          :disable="activeRun !== null"
          @keydown="onEditorKeydown"
        />
        <!-- What the next message is sent with, under the message itself. -->
        <div class="ai-conversation__tools">
          <AppIconButton
            icon="add"
            tooltip="Attach workspace tabs"
            data-testid="ai-attach-context"
            :disable="activeRun !== null || contexts.length === 0"
            @click="contextDialogShown = true"
          />
          <AppSelect
            class="ai-conversation__policy"
            compact
            :model-value="shownPolicy"
            :options="policyOptions"
            :disable="activeRun !== null"
            label="Changes"
            data-testid="ai-chat-policy"
            @update:model-value="choosePolicy"
          />
          <AiModelSelect
            class="ai-conversation__model"
            compact
            :model-value="chatModel"
            :disable="activeRun !== null"
            data-testid="ai-chat-model"
            @update:model-value="chooseModel"
          />
          <AppIconButton
            :icon="dictation.listening.value ? 'mic' : 'mic_none'"
            :active="dictation.listening.value"
            :tooltip="!dictation.supported
              ? 'This browser cannot listen'
              : dictation.listening.value ? 'Stop dictating' : 'Dictate the message'"
            :disable="!dictation.supported || activeRun !== null"
            data-testid="ai-dictate"
            @click="dictate"
          />
          <span class="ai-conversation__gap" />
          <AppButton
            v-if="activeRun"
            variant="danger-quiet"
            icon="stop"
            label="Stop"
            :loading="cancel.isPending.value"
            data-testid="ai-stop"
            @click="stop"
          />
          <AppButton
            v-else
            icon="send"
            label="Send"
            :disable="!canSend"
            data-testid="ai-send"
            @click="submit"
          />
        </div>
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
.ai-conversation__body { flex: 1; min-height: 0; display: flex; }
/* The messages hold the marks' coordinates: offsetTop is measured against this
   box, so it has to be the one they are positioned in. */
.ai-conversation__messages { position: relative; flex: 1; min-height: 0; overflow: auto; padding: var(--dp-space-4); }
.ai-outline { flex: none; display: flex; flex-direction: column; justify-content: center; gap: var(--dp-space-1); padding: var(--dp-space-2) var(--dp-space-1); overflow: hidden; }
/* The mark is two pixels of ink in a target a finger can hit. */
.ai-outline__mark { display: grid; place-items: center; width: 20px; height: 12px; border: 0; padding: 0; background: transparent; cursor: pointer; }
.ai-outline__mark::before { content: ""; width: 12px; height: 2px; border-radius: 1px; background: var(--dp-border-strong); transition: width 120ms ease, background-color 120ms ease; }
.ai-outline__mark:hover::before { background: var(--dp-text-muted); }
.ai-outline__mark--current::before { width: 16px; background: var(--dp-text-strong); }
.ai-conversation__empty { height: 100%; display: grid; place-content: center; justify-items: center; gap: var(--dp-space-2); color: var(--dp-text-muted); }
.ai-message { margin: 0 0 var(--dp-space-4); }
.ai-message--user { display: flex; flex-direction: column; align-items: flex-end; }
.ai-message__user { max-width: 78%; padding: var(--dp-space-2) var(--dp-space-3); white-space: pre-wrap; background: var(--dp-active); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); }
.ai-message__actions { display: flex; gap: var(--dp-space-1); margin-top: var(--dp-space-1); }
.ai-message__error { margin-top: var(--dp-space-2); }
.ai-steps { margin-bottom: var(--dp-space-2); color: var(--dp-text-muted); font-size: 12px; }
.ai-steps__summary, .ai-step__reasoning { border: 0; padding: 0; background: transparent; color: inherit; cursor: pointer; }
.ai-steps__summary { display: flex; align-items: center; gap: var(--dp-space-1); }
.ai-steps__list { margin: var(--dp-space-1) 0 0 var(--dp-space-4); }
.ai-step { display: grid; grid-template-columns: 1fr auto; gap: var(--dp-space-1) var(--dp-space-3); padding: var(--dp-space-1) 0; }
.ai-step__reasoning { grid-column: 1 / -1; width: fit-content; text-decoration: underline; }
.ai-step__detail { grid-column: 1 / -1; white-space: pre-wrap; color: var(--dp-text-strong); }
.ai-question { display: grid; gap: var(--dp-space-2); padding: var(--dp-space-3); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface); }
.ai-question__choices { display: flex; flex-wrap: wrap; gap: var(--dp-space-2); }
.ai-question__preview { display: grid; gap: var(--dp-space-1); padding: var(--dp-space-2) 0 0; font-size: 12px; color: var(--dp-text-muted); }
.ai-question__preview-summary { color: var(--dp-text-strong); }
.ai-question__preview-line { white-space: pre-wrap; }
.ai-conversation__composer { flex: none; display: flex; flex-direction: column; gap: var(--dp-space-2); padding: var(--dp-space-3); border-top: 1px solid var(--dp-border); }
.ai-conversation__contexts { display: flex; flex-wrap: wrap; gap: var(--dp-space-1); }
.ai-conversation__tools { display: flex; flex-wrap: wrap; align-items: center; gap: var(--dp-space-2); }
.ai-conversation__gap { flex: 1; }
/* Wide enough for a model's name and no wider: the row it stands in belongs
   to the send button at its end. */
.ai-conversation__model, .ai-conversation__policy { flex: 0 1 200px; min-width: 120px; }
.ai-context-chip { display: inline-flex; align-items: center; gap: var(--dp-space-1); padding-left: var(--dp-space-2); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-control); background: var(--dp-surface); color: var(--dp-text-strong); }
/* The box is one line until there is more to hold, and stops at eight of them
   rather than pushing the transcript off the card. A grown field scrolls; the
   corner grip is gone with it, because a hand-dragged height had no floor and
   no ceiling and was forgotten on every chat switch. */
.ai-conversation__composer :deep(textarea) { max-height: 8lh; }
</style>
