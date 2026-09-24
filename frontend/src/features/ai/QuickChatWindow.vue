<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, nextTick, ref, watch } from "vue"

import { AiService } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppInput, AppSelect, AppSpinner, useConfirm, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import AiModelSelect from "./AiModelSelect.vue"
import ChatMarkdown from "./ChatMarkdown.vue"
import { useAiSettings } from "./api"
import { explainRequest, quickChatIntent } from "./quickChatLauncher"

const toast = useToast()
const confirm = useConfirm()
const cache = useQueryClient()
const settings = useAiSettings()
const open = ref(false)
const selected = ref<string | null>(null)
const draft = ref("")
const busy = ref(false)
const scroller = ref<HTMLElement | null>(null)
const history = useQuery({
  queryKey: ["ai", "quick-chats"],
  queryFn: async () => (await AiService.listQuickChats()).data,
  enabled: open,
})
const chat = useQuery({
  queryKey: computed(() => ["ai", "quick-chat", selected.value]),
  queryFn: async () => (await AiService.readQuickChat({ path: { chat_id: selected.value as string } })).data,
  enabled: computed(() => open.value && selected.value !== null),
})
const modelKey = ref<string | null>(null)
const choices = computed(() => (history.data.value ?? []).map((item) => ({
  value: item.id, label: item.title,
})))
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
  open.value = true
  if (intent.kind === "open") {
    const found = await history.refetch()
    if (!selected.value && found.data?.length) selected.value = found.data[0]!.id
    return
  }
  try {
    const made = (await AiService.createQuickChat()).data
    await cache.invalidateQueries({ queryKey: ["ai", "quick-chats"] })
    selected.value = made.id
    draft.value = explainRequest(intent.text)
    await send()
  } catch (cause) {
    toast.error(messageOf(cause, "Quick chat could not be opened"))
  }
})

async function newChat() {
  if (selected.value && chat.data.value?.id === selected.value && !chat.data.value.messages.length) {
    draft.value = ""
    return
  }
  try {
    selected.value = (await AiService.createQuickChat()).data.id
    draft.value = ""
    await cache.invalidateQueries({ queryKey: ["ai", "quick-chats"] })
  } catch (cause) { toast.error(messageOf(cause, "Quick chat could not be created")) }
}

async function send(value = draft.value) {
  const text = value.trim()
  if (!text || busy.value) return
  busy.value = true
  try {
    const id = selected.value ?? (await AiService.createQuickChat()).data.id
    selected.value = id
    const result = (await AiService.sendQuickChatMessage({
      path: { chat_id: id }, body: { text, model_key: modelKey.value },
    })).data
    cache.setQueryData(["ai", "quick-chat", id], result)
    await cache.invalidateQueries({ queryKey: ["ai", "quick-chats"] })
    if (value === draft.value) draft.value = ""
  } catch (cause) { toast.error(messageOf(cause, "The model could not answer")) }
  finally { busy.value = false }
}

async function remove() {
  const id = selected.value
  if (!id || busy.value) return
  if (!(await confirm({
    title: "Delete quick chat?",
    message: "This quick chat and its messages will be deleted permanently.",
    confirmLabel: "Delete",
    danger: true,
  }))) return
  try {
    await AiService.deleteQuickChat({ path: { chat_id: id } })
    const found = await history.refetch()
    selected.value = found.data?.find((item) => item.id !== id)?.id ?? null
    cache.removeQueries({ queryKey: ["ai", "quick-chat", id] })
  } catch (cause) { toast.error(messageOf(cause, "Quick chat could not be deleted")) }
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
    title="Quick chat"
    size="form"
    sizing="stable"
    data-testid="quick-chat-window"
  >
    <div class="quick-chat">
      <div class="quick-chat__toolbar">
        <AppSelect
          class="quick-chat__history"
          label="Quick chats"
          :model-value="selected"
          :options="choices"
          :disable="busy"
          @update:model-value="selected = String($event)"
        />
        <AppButton label="New" variant="quiet" size="sm" :disable="busy" @click="newChat" />
        <AppButton label="Delete" variant="quiet" size="sm" :disable="!selected || busy" @click="remove" />
      </div>
      <div ref="scroller" class="quick-chat__messages" data-testid="quick-chat-messages">
        <AppSpinner v-if="chat.isPending.value && selected" />
        <AppBanner v-else-if="chat.isError.value" tone="error">The chat could not be loaded.</AppBanner>
        <div v-else-if="!chat.data.value?.messages.length" class="quick-chat__empty">
          Ask anything. This chat does not use agent tools or application data.
        </div>
        <article
          v-for="message in chat.data.value?.messages ?? []"
          :key="message.id"
          class="quick-chat__message"
          :class="`quick-chat__message--${message.role}`"
        >
          <div v-if="message.role === 'user'" class="quick-chat__question">{{ message.content }}</div>
          <ChatMarkdown v-else :text="message.content" />
        </article>
        <AppSpinner v-if="busy" />
      </div>
      <div class="quick-chat__composer">
        <AiModelSelect v-model="modelKey" :allow-auto="false" />
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
        <AppButton label="Send" :disable="busy || !draft.trim()" @click="send()" />
      </div>
    </div>
  </WindowDialog>
</template>

<style scoped>
.quick-chat { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.quick-chat__toolbar { display: flex; align-items: center; gap: var(--dp-space-2); padding: var(--dp-space-2); border-bottom: 1px solid var(--dp-border); }
.quick-chat__history { flex: 1; min-width: 0; }
.quick-chat__messages { flex: 1; min-height: 0; overflow: auto; padding: var(--dp-space-3); }
.quick-chat__empty { height: 100%; display: grid; place-items: center; color: var(--dp-text-muted); text-align: center; }
.quick-chat__message { margin-bottom: var(--dp-space-3); }
.quick-chat__message--user { display: flex; justify-content: flex-end; }
.quick-chat__question { max-width: 85%; white-space: pre-wrap; padding: var(--dp-space-2) var(--dp-space-3); background: var(--dp-active); border-radius: var(--dp-radius-panel); }
.quick-chat__composer { display: grid; gap: var(--dp-space-2); padding: var(--dp-space-2); border-top: 1px solid var(--dp-border); }
</style>
