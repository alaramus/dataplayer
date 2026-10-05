<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { ConversationSummary, QuickChatSummary } from "@/client"

import { AppBanner, AppButton, AppEmptyState, AppForm, AppIconButton, AppSpinner, AppToggle, AppTooltip, useConfirm, useToast } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import AiModelSelect from "./AiModelSelect.vue"
import AiKeyDialog from "./AiKeyDialog.vue"
import VoiceSelect from "@/features/speech/VoiceSelect.vue"
import { speechSupported } from "@/features/speech/voices"
import {
  useAiSettings,
  useAiModels,
  useArchivedAiConversations,
  useArchivedQuickChats,
  useDeleteAiConversation,
  useDeleteArchivedAiConversations,
  useDeleteQuickChat,
  useDeleteArchivedQuickChats,
  useUpdateAiConversation,
  useUpdateQuickChat,
  useUpdateAiSettings,
} from "./api"
import { autoModelValue, fallbackModel } from "./modelOptions"

const settings = useAiSettings()
const models = useAiModels()
const update = useUpdateAiSettings()
// The voice reading aloud, chosen here as in Preferences: voices are this
// browser's own, and one store serves both controls.
const speechOk = speechSupported()
const archive = useArchivedAiConversations()
const quickArchive = useArchivedQuickChats()
const updateConversation = useUpdateAiConversation()
const updateQuickChat = useUpdateQuickChat()
const deleteConversation = useDeleteAiConversation()
const deleteQuickChat = useDeleteQuickChat()
const deleteArchived = useDeleteArchivedAiConversations()
const deleteArchivedQuick = useDeleteArchivedQuickChats()
const confirm = useConfirm()
const toast = useToast()
const modelValue = computed(() => settings.data.value?.auto_provider
  ? autoModelValue(settings.data.value.auto_provider)
  : settings.data.value?.model_key ?? null)
const allowAll = computed(() => settings.data.value?.allow_all_changes ?? false)
const jevKeySet = computed(() => settings.data.value?.keys.some((key) => key.provider === "typesafe" && key.set) ?? false)
const jevDialogOpen = ref(false)
type ArchivedChat = { kind: "agent"; chat: ConversationSummary } | { kind: "quick"; chat: QuickChatSummary }
const archived = computed<ArchivedChat[]>(() => [
  ...(archive.data.value?.data ?? []).map((chat): ArchivedChat => ({ kind: "agent", chat })),
  ...(quickArchive.data.value ?? []).map((chat): ArchivedChat => ({ kind: "quick", chat })),
].sort((a, b) => (b.chat.updated_at ?? "").localeCompare(a.chat.updated_at ?? "")))

async function chooseModel(value: string) {
  const provider = models.data.value?.find((one) => value === autoModelValue(one.provider))?.provider
  const fallback = provider ? fallbackModel(models.data.value ?? [], settings.data.value?.model_key ?? null, provider) : null
  if (provider && !fallback) return
  try { await update.mutateAsync({ model_key: fallback?.key ?? value, auto_provider: provider ?? null }) }
  catch (cause) { toast.error(messageOf(cause, "The model could not be selected")) }
}
async function setAllowAll(value: boolean) {
  try { await update.mutateAsync({ allow_all_changes: value }) }
  catch (cause) { toast.error(messageOf(cause, "The confirmation setting could not be changed")) }
}
async function restore(entry: ArchivedChat) {
  try {
    if (entry.kind === "agent") await updateConversation.mutateAsync({ id: entry.chat.id, archived: false })
    else await updateQuickChat.mutateAsync({ id: entry.chat.id, archived: false })
    toast.success("Chat restored")
  }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be restored")) }
}
async function remove(entry: ArchivedChat) {
  if (!(await confirm({ title: "Delete chat?", message: `“${entry.chat.title}” will be permanently deleted.`, confirmLabel: "Delete", danger: true }))) return
  try {
    if (entry.kind === "agent") await deleteConversation.mutateAsync(entry.chat.id)
    else await deleteQuickChat.mutateAsync(entry.chat.id)
  }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be deleted")) }
}
async function removeAll() {
  const count = archived.value.length
  if (!(await confirm({ title: "Empty the archive?", message: `${String(count)} ${count === 1 ? "chat" : "chats"} will be permanently deleted.`, confirmLabel: "Delete all", danger: true }))) return
  try {
    if (archive.data.value?.data.length) await deleteArchived.mutateAsync()
    if (quickArchive.data.value?.length) await deleteArchivedQuick.mutateAsync()
  }
  catch (cause) { toast.error(messageOf(cause, "The chats could not be deleted")) }
}
</script>

<template>
  <div
    class="ai-settings"
    data-testid="ai-settings"
  >
    <AppSpinner v-if="settings.isPending.value" />
    <AppBanner
      v-else-if="settings.isError.value"
      tone="error"
    >
      Agent settings could not be loaded.
    </AppBanner>
    <template v-else>
      <section class="ai-settings__group">
        <AppForm
          layout="section"
          class="ai-settings__form"
        >
          <AppBanner
            v-if="settings.data.value?.model_missing"
            tone="warning"
          >
            The saved model is no longer available. Choose another one.
          </AppBanner>
          <AiModelSelect
            :model-value="modelValue"
            key-button
            :hint="false"
            data-testid="ai-model"
            @update:model-value="chooseModel"
          />
          <VoiceSelect
            v-if="speechOk"
            label="Reading voice"
            data-testid="ai-voice"
          />
        </AppForm>
      </section>
      <section class="ai-settings__group">
        <AppForm
          layout="section"
          class="ai-settings__form"
        >
          <h3>Confirmations</h3>
          <AppToggle
            :model-value="allowAll"
            label="Allow all changes in every chat"
            data-testid="ai-allow-all"
            @update:model-value="setAllowAll"
          />
          <AppButton
            class="ai-settings__jev"
            variant="quiet"
            :label="jevKeySet ? 'Manage Jev API key' : 'Set Jev API key'"
            data-testid="ai-jev-key"
            @click="jevDialogOpen = true"
          />
        </AppForm>
      </section>
      <AiKeyDialog
        v-model="jevDialogOpen"
        provider="typesafe"
        provider-label="TypeSafe (Jev)"
        :key-set="jevKeySet"
      />
      <section class="ai-settings__archive">
        <h3>Archive</h3>
        <AppSpinner v-if="archive.isPending.value || quickArchive.isPending.value" />
        <AppBanner
          v-else-if="archive.isError.value || quickArchive.isError.value"
          tone="error"
        >
          The archive could not be loaded.
        </AppBanner>
        <AppEmptyState
          v-else-if="!archived.length"
          icon="archive"
          text="Chats you archive are kept here until you delete them."
        />
        <template v-else>
          <div class="ai-settings__archived-list">
            <div
              v-for="entry in archived"
              :key="`${entry.kind}-${entry.chat.id}`"
              class="ai-archived"
              :data-testid="`ai-archived-${entry.chat.id}`"
            >
              <span class="ai-archived__title">
                {{ entry.chat.title }}
                <AppTooltip>{{ entry.chat.title }}</AppTooltip>
              </span>
              <AppIconButton
                :icon="appIcons.unarchive"
                tooltip="Restore chat"
                :data-testid="`ai-restore-${entry.chat.id}`"
                @click="restore(entry)"
              />
              <AppIconButton
                :icon="appIcons.delete"
                tooltip="Delete chat"
                variant="danger-quiet"
                :data-testid="`ai-delete-${entry.chat.id}`"
                @click="remove(entry)"
              />
            </div>
          </div>
          <AppButton
            class="ai-settings__delete-all"
            variant="danger-quiet"
            size="sm"
            label="Delete all"
            data-testid="ai-delete-all"
            @click="removeAll"
          />
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
/* Under the card's head, which names it. */
.ai-settings { flex: 1; min-height: 0; overflow: auto; }
.ai-settings h3 { font-weight: 600; }
.ai-settings__group { border-bottom: 1px solid var(--dp-border-faint); }
.ai-settings__form { max-width: 640px; }
/* A command under a toggle starts where the toggle does; stretched across
   the form, its label stood alone in the middle. */
.ai-settings__jev { align-self: flex-start; }
.ai-settings__archive { display: flex; flex-direction: column; gap: var(--dp-space-3); max-width: 640px; padding: var(--dp-space-4); }
.ai-settings__archived-list { display: flex; flex-direction: column; }
.ai-settings__delete-all { align-self: flex-start; }
.ai-archived { display: flex; align-items: center; gap: var(--dp-space-1); min-width: 0; padding: var(--dp-space-2) 0; }
.ai-archived + .ai-archived { border-top: 1px solid var(--dp-border-faint); }
.ai-archived__title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
