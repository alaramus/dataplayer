<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

import { AiService } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { realtime } from "@/shared/realtime/client"
import { AppBanner, AppButton, AppIconButton, AppInput, AppSpinner, appIcons, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import AiMessageActions from "./AiMessageActions.vue"
import AiModelSelect from "./AiModelSelect.vue"
import ChatMarkdown from "./ChatMarkdown.vue"
import { aiSettingsKey, quickChatsKey, useAiSettings, useUpdateAiSettings } from "./api"
import { useDictation } from "./dictation"
import { deletedQuickChat, explainRequest, explainTitle, quickChatIntent } from "./quickChatLauncher"

const toast = useToast()
const cache = useQueryClient()
const settings = useAiSettings()
const open = ref(false)
const selected = ref<string | null>(null)
const draft = ref("")
watch(deletedQuickChat, (id) => {
  if (id !== selected.value) return
  selected.value = null
  draft.value = ""
  open.value = false
}, { flush: "sync" })
const busy = ref(false)
const scroller = ref<HTMLElement | null>(null)
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
watch(open, (value) => { if (!value) dictation.stop() })
onBeforeUnmount(() => dictation.stop())
const chat = useQuery({
  queryKey: computed(() => ["ai", "quick-chat", selected.value]),
  queryFn: async () => (await AiService.readQuickChat({ path: { chat_id: selected.value as string } })).data,
  enabled: computed(() => open.value && selected.value !== null),
})
const modelKey = ref<string | null>(null)
const updateSettings = useUpdateAiSettings()
/**
 * An explicit pick is the person's choice everywhere (D140), not only for
 * this window: the settings keep it, so a reload still opens on it.
 */
async function chooseModel(value: string) {
  modelKey.value = value
  try { await updateSettings.mutateAsync({ model_key: value }) }
  catch (cause) { toast.error(messageOf(cause, "The model could not be chosen")) }
}
const title = computed(() => chat.data.value?.id === selected.value ? chat.data.value.title : "New chat")
watch(() => chat.data.value?.model_key, (key) => { if (key) modelKey.value = key })
watch(() => settings.data.value?.model_key, (key) => {
  if (!modelKey.value && key) modelKey.value = key
}, { immediate: true })
watch(() => chat.data.value?.messages.length, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
})

/**
 * The question being answered and the answer so far (D158).
 *
 * Drawn after the saved messages until the send returns the chat, which is the
 * authority: a delta the socket missed is only a moment of text.
 */
const asked = ref<string | null>(null)
const answer = ref("")
// The question is committed before the model is called, so a chat read in the
// meantime may already hold it.
const askedShown = computed(() => {
  const last = chat.data.value?.messages.at(-1)
  return asked.value !== null && !(last?.role === "user" && last.content === asked.value)
})
const stopListening = realtime().subscribe("ai.quick", (payload) => {
  if (asked.value === null || typeof payload !== "object" || payload === null) return
  const delta = payload as { chat_id?: unknown; text?: unknown }
  if (delta.chat_id === selected.value && typeof delta.text === "string") answer.value += delta.text
})
onBeforeUnmount(stopListening)
watch(asked, async (question) => {
  if (question === null) return
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
})
// Follows the answer down while the reader is at the bottom, and leaves them
// where they are once they have scrolled up to read.
watch(answer, async () => {
  const box = scroller.value
  if (box === null) return
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 48
  await nextTick()
  if (atBottom) box.scrollTop = box.scrollHeight
})
watch(() => quickChatIntent.value?.id, async () => {
  const intent = quickChatIntent.value?.request
  if (!intent) return
  dictation.stop()
  open.value = true
  if (intent.kind === "chat") {
    selected.value = intent.id
    draft.value = ""
    return
  }
  selected.value = null
  draft.value = ""
  if (intent.kind === "explain") {
    draft.value = explainRequest(intent.text)
    await send(draft.value, explainTitle(intent.text))
  }
})

/** A new chat, named when the caller knows better than its first line. */
async function createChat(title: string | null): Promise<string> {
  const id = (await AiService.createQuickChat()).data.id
  if (title !== null) {
    try {
      await AiService.updateQuickChat({ path: { chat_id: id }, body: { title } })
    } catch {
      // Unnamed, the server names it by the first line of the question.
    }
  }
  return id
}

async function send(value = draft.value, title: string | null = null) {
  const text = value.trim()
  if (!text || busy.value) return
  busy.value = true
  dictation.stop()
  // Out of the composer as it goes into the transcript; put back below if the
  // server cannot say it kept the question.
  const typed = value === draft.value
  if (typed) draft.value = ""
  asked.value = text
  answer.value = ""
  let created: string | null = null
  const beforeCount = chat.data.value?.id === selected.value ? chat.data.value.messages.length : 0
  try {
    const id = selected.value ?? (await createChat(title))
    if (selected.value === null) created = id
    selected.value = id
    const result = (await AiService.sendQuickChatMessage({
      path: { chat_id: id }, body: { text, model_key: modelKey.value },
    })).data
    cache.setQueryData(["ai", "quick-chat", id], result)
    await cache.invalidateQueries({ queryKey: quickChatsKey })
    // The server remembers an explicitly chosen model as the person's choice
    // (D140): let the settings, and every composer reading them, follow.
    await cache.invalidateQueries({ queryKey: aiSettingsKey })
  } catch (cause) {
    let kept = false
    const id = created ?? selected.value
    if (id !== null) {
      try {
        const saved = (await AiService.readQuickChat({ path: { chat_id: id } })).data
        if (saved.messages.length > beforeCount && saved.messages.some((message) => message.role === "user" && message.content === text)) {
          cache.setQueryData(["ai", "quick-chat", id], saved)
          await cache.invalidateQueries({ queryKey: quickChatsKey })
          kept = true
        } else if (created !== null) {
          await AiService.deleteQuickChat({ path: { chat_id: id } })
          selected.value = null
        }
      } catch { /* Keep the draft and chat ID when the server cannot confirm what was saved. */ }
    }
    if (!kept && typed && !draft.value) draft.value = value
    toast.error(messageOf(cause, "The model could not answer"))
  }
  finally {
    busy.value = false
    asked.value = null
    answer.value = ""
  }
}

function editorKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void send()
  }
}
</script>

<template>
  <WindowDialog
    v-model="open"
    :title="title"
    size="chat"
    sizing="stable"
    data-testid="quick-chat-window"
  >
    <div class="quick-chat">
      <div
        ref="scroller"
        class="quick-chat__messages"
        data-testid="quick-chat-messages"
      >
        <div class="quick-chat__transcript">
          <AppSpinner v-if="chat.isPending.value && selected" />
          <AppBanner
            v-else-if="chat.isError.value"
            tone="error"
          >
            The chat could not be loaded.
          </AppBanner>
          <div
            v-else-if="!chat.data.value?.messages.length && asked === null"
            class="quick-chat__empty"
          >
            <q-icon
              :name="appIcons.autoAwesome"
              size="var(--dp-icon-xl)"
            />
            <span>What would you like to know?</span>
          </div>
          <article
            v-for="message in chat.data.value?.messages ?? []"
            :key="message.id"
            class="quick-chat__message"
            :class="`quick-chat__message--${message.role}`"
          >
            <div
              v-if="message.role === 'user'"
              class="quick-chat__question"
            >
              {{ message.content }}
            </div>
            <ChatMarkdown
              v-else
              :text="message.content"
            />
            <AiMessageActions
              class="quick-chat__actions"
              :text="message.content"
              :role="message.role"
            />
          </article>
          <article
            v-if="askedShown"
            class="quick-chat__message quick-chat__message--user"
          >
            <div class="quick-chat__question">
              {{ asked }}
            </div>
          </article>
          <article
            v-if="asked !== null"
            class="quick-chat__message quick-chat__message--assistant"
            data-testid="quick-chat-answering"
          >
            <ChatMarkdown
              v-if="answer"
              :text="answer"
            />
            <AppSpinner v-else />
          </article>
        </div>
        <div class="quick-chat__dock">
          <div class="quick-chat__composer">
            <AppInput
              v-model="draft"
              type="textarea"
              grow
              compact
              placeholder="Message the model"
              aria-label="Quick chat message"
              data-testid="quick-chat-input"
              :disable="busy"
              @keydown="editorKeydown"
            />
            <div class="quick-chat__tools">
              <AiModelSelect
                :model-value="modelKey"
                :pending="selected !== null && chat.isPending.value"
                class="quick-chat__model"
                compact
                :allow-auto="false"
                :disable="busy"
                @update:model-value="chooseModel"
              />
              <AppIconButton
                :icon="dictation.listening.value ? appIcons.mic : appIcons.micNone"
                :active="dictation.listening.value"
                :tooltip="!dictation.supported
                  ? 'This browser cannot listen'
                  : dictation.listening.value ? 'Stop dictating' : 'Dictate the message'"
                :disable="!dictation.supported || busy"
                data-testid="quick-chat-dictate"
                @click="dictate"
              />
              <span class="quick-chat__gap" />
              <AppButton
                :icon="appIcons.send"
                label="Send"
                icon-only
                :disable="busy || !draft.trim()"
                data-testid="quick-chat-send"
                @click="send()"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </WindowDialog>
</template>

<style scoped>
.quick-chat { height: 100%; min-height: 0; display: flex; flex-direction: column; }
/* Laid out as the agent's chat is (AiConversation): the transcript scrolls the
   whole height of the window and passes under the composer. */
.quick-chat__messages { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }
.quick-chat__transcript { flex: 1 0 auto; padding: var(--dp-space-5) var(--dp-space-4) 0; isolation: isolate; }
.quick-chat__empty { min-height: 100%; display: grid; place-content: center; justify-items: center; gap: var(--dp-space-2); color: var(--dp-text-muted); }
.quick-chat__message { max-width: 960px; margin: 0 auto var(--dp-space-4); }
.quick-chat__message--user { display: flex; flex-direction: column; align-items: flex-end; }
/* Shown under the message the pointer is on, as in the agent's chat. */
.quick-chat__actions { margin-top: var(--dp-space-1); opacity: 0; pointer-events: none; transition: opacity 120ms ease; }
.quick-chat__message:hover .quick-chat__actions, .quick-chat__message:focus-within .quick-chat__actions { opacity: 1; pointer-events: auto; }
@media (hover: none) { .quick-chat__actions { opacity: 1; pointer-events: auto; } }
.quick-chat__question { max-width: 78%; font-size: var(--dp-prose-font-size); line-height: 1.65; white-space: pre-wrap; padding: var(--dp-space-2) var(--dp-space-3); background: var(--dp-active); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); }
.quick-chat__dock { position: sticky; bottom: 0; flex: none; padding: var(--dp-space-2) var(--dp-space-4) var(--dp-space-3); background: linear-gradient(transparent, var(--dp-surface-raised) var(--dp-space-2)); }
.quick-chat__composer { box-sizing: border-box; display: flex; flex-direction: column; gap: var(--dp-space-2); max-width: 960px; margin: 0 auto; padding: var(--dp-space-3); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface-raised); box-shadow: 0 8px 24px var(--dp-shadow-soft); }
.quick-chat__tools { display: flex; align-items: center; gap: var(--dp-space-2); }
.quick-chat__model { flex: 0 1 200px; min-width: 120px; }
.quick-chat__gap { flex: 1; }
.quick-chat__composer :deep(.q-field__control) { background: transparent; }
.quick-chat__composer :deep(.q-field__control::before) { border-color: transparent; }
.quick-chat__composer :deep(.q-field--focused .q-field__control::after) { border-color: var(--dp-field-border); }
.quick-chat__composer :deep(textarea) { max-height: 8lh; }
</style>
