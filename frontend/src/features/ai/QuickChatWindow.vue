<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

import { AiService } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppIconButton, AppInput, AppSpinner, appIcons, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import AiModelSelect from "./AiModelSelect.vue"
import ChatMarkdown from "./ChatMarkdown.vue"
import { quickChatsKey, useAiSettings } from "./api"
import { useDictation } from "./dictation"
import { deletedQuickChat, explainRequest, quickChatIntent } from "./quickChatLauncher"

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
const title = computed(() => chat.data.value?.id === selected.value ? chat.data.value.title : "New chat")
watch(() => chat.data.value?.model_key, (key) => { if (key) modelKey.value = key })
watch(() => settings.data.value?.model_key, (key) => {
  if (!modelKey.value && key) modelKey.value = key
}, { immediate: true })
watch(() => chat.data.value?.messages.length, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
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
    await send()
  }
})

async function send(value = draft.value) {
  const text = value.trim()
  if (!text || busy.value) return
  busy.value = true
  dictation.stop()
  let created: string | null = null
  const beforeCount = chat.data.value?.id === selected.value ? chat.data.value.messages.length : 0
  try {
    const id = selected.value ?? (await AiService.createQuickChat()).data.id
    if (selected.value === null) created = id
    selected.value = id
    const result = (await AiService.sendQuickChatMessage({
      path: { chat_id: id }, body: { text, model_key: modelKey.value },
    })).data
    cache.setQueryData(["ai", "quick-chat", id], result)
    await cache.invalidateQueries({ queryKey: quickChatsKey })
    if (value === draft.value) draft.value = ""
  } catch (cause) {
    const id = created ?? selected.value
    if (id !== null) {
      try {
        const saved = (await AiService.readQuickChat({ path: { chat_id: id } })).data
        if (saved.messages.length > beforeCount && saved.messages.some((message) => message.role === "user" && message.content === text)) {
          cache.setQueryData(["ai", "quick-chat", id], saved)
          await cache.invalidateQueries({ queryKey: quickChatsKey })
          if (value === draft.value) draft.value = ""
        } else if (created !== null) {
          await AiService.deleteQuickChat({ path: { chat_id: id } })
          selected.value = null
        }
      } catch { /* Keep the draft and chat ID when the server cannot confirm what was saved. */ }
    }
    toast.error(messageOf(cause, "The model could not answer"))
  }
  finally { busy.value = false }
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
        <AppSpinner v-if="chat.isPending.value && selected" />
        <AppBanner
          v-else-if="chat.isError.value"
          tone="error"
        >
          The chat could not be loaded.
        </AppBanner>
        <div
          v-else-if="!chat.data.value?.messages.length"
          class="quick-chat__empty"
        >
          <q-icon
            :name="appIcons.autoAwesome"
            size="30px"
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
        </article>
        <AppSpinner v-if="busy" />
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
              v-model="modelKey"
              class="quick-chat__model"
              compact
              :allow-auto="false"
              :disable="busy"
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
  </WindowDialog>
</template>

<style scoped>
.quick-chat { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.quick-chat__messages { flex: 1; min-height: 0; overflow: auto; padding: var(--dp-space-5) var(--dp-space-4); }
.quick-chat__empty { height: 100%; display: grid; place-content: center; justify-items: center; gap: var(--dp-space-2); color: var(--dp-text-muted); }
.quick-chat__message { max-width: 960px; margin: 0 auto var(--dp-space-4); }
.quick-chat__message--user { display: flex; justify-content: flex-end; }
.quick-chat__question { max-width: 78%; white-space: pre-wrap; padding: var(--dp-space-2) var(--dp-space-3); background: var(--dp-active); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); }
.quick-chat__dock { flex: none; padding: var(--dp-space-2) var(--dp-space-4) var(--dp-space-3); }
.quick-chat__composer { box-sizing: border-box; display: flex; flex-direction: column; gap: var(--dp-space-2); max-width: 960px; margin: 0 auto; padding: var(--dp-space-3); border: 1px solid var(--dp-border); border-radius: var(--dp-radius-panel); background: var(--dp-surface-raised); box-shadow: 0 8px 24px var(--dp-shadow-soft); }
.quick-chat__tools { display: flex; align-items: center; gap: var(--dp-space-2); }
.quick-chat__model { flex: 0 1 200px; min-width: 120px; }
.quick-chat__gap { flex: 1; }
.quick-chat__composer :deep(.q-field__control) { background: transparent; }
.quick-chat__composer :deep(.q-field__control::before) { border-color: transparent; }
.quick-chat__composer :deep(.q-field--focused .q-field__control::after) { border-color: var(--dp-field-border); }
.quick-chat__composer :deep(textarea) { max-height: 8lh; }
</style>
