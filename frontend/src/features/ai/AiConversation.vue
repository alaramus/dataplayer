<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

import type { AgentRunPublic, ConversationMessagePublic } from "@/client"
import { AppBanner, AppButton, AppIconButton, AppInput, AppSpinner, useToast } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import ChatMarkdown from "./ChatMarkdown.vue"
import { plainSpeechText } from "./streaming"
import { useAiConversation, useCancelAiRun, useSendAiMessage } from "./api"

const props = defineProps<{ conversationId: string }>()
const conversation = useAiConversation(() => props.conversationId)
const send = useSendAiMessage()
const cancel = useCancelAiRun()
const toast = useToast()
const draft = ref("")
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

function runFor(message: ConversationMessagePublic): AgentRunPublic | undefined {
  return message.run_id ? runs.value.get(message.run_id) : undefined
}
function duration(run: AgentRunPublic): string {
  if (!run.created_at) return ""
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now()
  const seconds = Math.max(0, Math.round((end - new Date(run.created_at).getTime()) / 1000))
  return `${String(seconds)} s`
}
function stepSummary(run: AgentRunPublic): string {
  const steps = run.steps ?? []
  const current = steps.find((step) => step.status === "running")
  if (current) return `${current.title} · ${duration(run)}`
  return `${String(steps.length)} ${steps.length === 1 ? "step" : "steps"}${duration(run) ? ` · ${duration(run)}` : ""}`
}
function toggle(set: Set<string>, id: string) {
  const next = new Set(set)
  next.has(id) ? next.delete(id) : next.add(id)
  if (set === expandedSteps.value) expandedSteps.value = next
  else expandedReasoning.value = next
}
async function submit() {
  const text = draft.value.trim()
  if (!canSend.value) return
  draft.value = ""
  try { await send.mutateAsync({ id: props.conversationId, text }) }
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
async function copy(text: string) {
  try { await navigator.clipboard.writeText(text); toast.success("Answer copied") }
  catch { toast.error("The answer could not be copied") }
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
}, { deep: true })
onBeforeUnmount(() => { if (speech) window.speechSynthesis.cancel() })
</script>

<template>
  <div class="ai-conversation">
    <AppSpinner v-if="conversation.isPending.value" />
    <AppBanner v-else-if="conversation.isError.value" tone="error">This conversation could not be loaded.</AppBanner>
    <template v-else>
      <div ref="scroller" class="ai-conversation__messages" data-testid="ai-messages">
        <div v-if="!conversation.data.value?.messages.length && !activeRun" class="ai-conversation__empty">
          <q-icon name="auto_awesome" size="32px" />
          <span>What would you like to know?</span>
        </div>
        <article v-for="message in conversation.data.value?.messages ?? []" :key="message.id" class="ai-message" :class="`ai-message--${message.role}`">
          <div v-if="message.role === 'assistant' && runFor(message)" class="ai-steps">
            <button type="button" class="ai-steps__summary" :aria-expanded="expandedSteps.has(runFor(message)!.id)" @click="toggle(expandedSteps, runFor(message)!.id)">
              <q-icon :name="expandedSteps.has(runFor(message)!.id) ? 'expand_more' : 'chevron_right'" />
              {{ stepSummary(runFor(message)!) }}
            </button>
            <div v-if="expandedSteps.has(runFor(message)!.id)" class="ai-steps__list">
              <div v-for="step in runFor(message)!.steps ?? []" :key="step.ordinal" class="ai-step">
                <span>{{ step.title }}</span><span>{{ step.status }}</span>
                <button v-if="step.detail" type="button" class="ai-step__reasoning" @click="toggle(expandedReasoning, `${runFor(message)!.id}:${String(step.ordinal)}`)">Thinking</button>
                <div v-if="step.detail && expandedReasoning.has(`${runFor(message)!.id}:${String(step.ordinal)}`)" class="ai-step__detail">{{ step.detail }}</div>
              </div>
            </div>
          </div>
          <div v-if="message.role === 'user'" class="ai-message__user">{{ message.content }}</div>
          <ChatMarkdown v-else :text="message.content" />
          <div v-if="message.role === 'assistant'" class="ai-message__actions">
            <AppIconButton icon="content_copy" tooltip="Copy answer" @click="copy(message.content)" />
            <AppIconButton icon="volume_up" tooltip="Listen to answer" @click="listen(message.content)" />
          </div>
        </article>
        <article v-if="activeRun" class="ai-message ai-message--assistant" data-testid="ai-streaming-answer">
          <div class="ai-steps">
            <button type="button" class="ai-steps__summary" :aria-expanded="expandedSteps.has(activeRun.id)" @click="toggle(expandedSteps, activeRun.id)">
              <q-icon :name="expandedSteps.has(activeRun.id) ? 'expand_more' : 'chevron_right'" />{{ stepSummary(activeRun) }}
            </button>
            <div v-if="expandedSteps.has(activeRun.id)" class="ai-steps__list">
              <div v-for="step in activeRun.steps ?? []" :key="step.ordinal" class="ai-step">
                <span>{{ step.title }}</span><span>{{ step.status }}</span>
                <button v-if="step.detail" type="button" class="ai-step__reasoning" @click="toggle(expandedReasoning, `${activeRun.id}:${String(step.ordinal)}`)">Thinking</button>
                <div v-if="step.detail && expandedReasoning.has(`${activeRun.id}:${String(step.ordinal)}`)" class="ai-step__detail">{{ step.detail }}</div>
              </div>
            </div>
          </div>
          <ChatMarkdown v-if="activeRun.partial_answer" :text="activeRun.partial_answer" />
        </article>
        <AppBanner v-for="run in unrepresentedRuns" :key="run.id" :tone="run.status === 'cancelled' ? 'info' : 'warning'" data-testid="ai-run-ended">
          {{ run.error || (run.status === "cancelled" ? "The answer was stopped." : `The answer was ${run.status}.`) }}
        </AppBanner>
      </div>
      <div class="ai-conversation__composer">
        <AppInput v-model="draft" type="textarea" compact placeholder="Message the agent" aria-label="Message the agent" data-testid="ai-message-input" :disable="activeRun !== null" @keydown="onEditorKeydown" />
        <AppButton v-if="activeRun" variant="danger-quiet" icon="stop" label="Stop" :loading="cancel.isPending.value" data-testid="ai-stop" @click="stop" />
        <AppButton v-else icon="send" label="Send" :disable="!canSend" data-testid="ai-send" @click="submit" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.ai-conversation { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.ai-conversation__messages { flex: 1; min-height: 0; overflow: auto; padding: var(--dp-space-4); }
.ai-conversation__empty { height: 100%; display: grid; place-content: center; justify-items: center; gap: var(--dp-space-2); color: var(--dp-text-muted); }
.ai-message { margin: 0 0 var(--dp-space-4); }
.ai-message--user { display: flex; justify-content: flex-end; }
.ai-message__user { max-width: 78%; padding: var(--dp-space-2) var(--dp-space-3); white-space: pre-wrap; background: var(--dp-active); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); }
.ai-message__actions { display: flex; gap: var(--dp-space-1); margin-top: var(--dp-space-1); }
.ai-steps { margin-bottom: var(--dp-space-2); color: var(--dp-text-muted); font-size: 12px; }
.ai-steps__summary, .ai-step__reasoning { border: 0; padding: 0; background: transparent; color: inherit; cursor: pointer; }
.ai-steps__summary { display: flex; align-items: center; gap: var(--dp-space-1); }
.ai-steps__list { margin: var(--dp-space-1) 0 0 var(--dp-space-4); }
.ai-step { display: grid; grid-template-columns: 1fr auto; gap: var(--dp-space-1) var(--dp-space-3); padding: var(--dp-space-1) 0; }
.ai-step__reasoning { grid-column: 1 / -1; width: fit-content; text-decoration: underline; }
.ai-step__detail { grid-column: 1 / -1; white-space: pre-wrap; color: var(--dp-text-strong); }
.ai-conversation__composer { flex: none; display: flex; align-items: flex-end; gap: var(--dp-space-2); padding: var(--dp-space-3); border-top: 1px solid var(--dp-border); }
.ai-conversation__composer :deep(.q-field) { flex: 1; }
</style>
