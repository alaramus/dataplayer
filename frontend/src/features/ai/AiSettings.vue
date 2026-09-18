<script setup lang="ts">
import { computed } from "vue"

import { AppBanner, AppButton, AppEmptyState, AppIconButton, AppSection, AppSpinner, AppToggle, useConfirm, useToast } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import AiModelSelect from "./AiModelSelect.vue"
import {
  useAiSettings,
  useArchivedAiConversations,
  useDeleteAiConversation,
  useDeleteArchivedAiConversations,
  useUpdateAiConversation,
  useUpdateAiSettings,
} from "./api"
const settings = useAiSettings()
const update = useUpdateAiSettings()
const archive = useArchivedAiConversations()
const updateConversation = useUpdateAiConversation()
const deleteConversation = useDeleteAiConversation()
const deleteArchived = useDeleteArchivedAiConversations()
const confirm = useConfirm()
const toast = useToast()
const modelValue = computed(() => settings.data.value?.model_key ?? null)
const allowAll = computed(() => settings.data.value?.allow_all_changes ?? false)
const archived = computed(() => archive.data.value?.data ?? [])

async function chooseModel(value: string) {
  try { await update.mutateAsync({ model_key: value }) }
  catch (cause) { toast.error(messageOf(cause, "The model could not be selected")) }
}
async function setAllowAll(value: boolean) {
  try { await update.mutateAsync({ allow_all_changes: value }) }
  catch (cause) { toast.error(messageOf(cause, "The confirmation setting could not be changed")) }
}
async function restore(id: string) {
  try { await updateConversation.mutateAsync({ id, archived: false }); toast.success("Chat restored") }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be restored")) }
}
async function remove(id: string, title: string) {
  if (!(await confirm({ title: "Delete chat?", message: `“${title}” will be permanently deleted.`, confirmLabel: "Delete", danger: true }))) return
  try { await deleteConversation.mutateAsync(id) }
  catch (cause) { toast.error(messageOf(cause, "The chat could not be deleted")) }
}
async function removeAll() {
  const count = archived.value.length
  if (!(await confirm({ title: "Empty the archive?", message: `${String(count)} ${count === 1 ? "chat" : "chats"} will be permanently deleted.`, confirmLabel: "Delete all", danger: true }))) return
  try { await deleteArchived.mutateAsync() }
  catch (cause) { toast.error(messageOf(cause, "The chats could not be deleted")) }
}
</script>

<template>
  <div
    class="ai-settings"
    data-testid="ai-settings"
  >
    <h2>Settings</h2>
    <AppSpinner v-if="settings.isPending.value || models.isPending.value" />
    <AppBanner
      v-else-if="settings.isError.value || models.isError.value"
      tone="error"
    >
      Agent settings could not be loaded.
    </AppBanner>
    <template v-else>
      <AppSection gutter>
        <h3>Model</h3>
        <AppBanner
          v-if="settings.data.value?.model_missing"
          tone="warning"
        >
          The saved model is no longer available. Choose another one.
        </AppBanner>
        <AiModelSelect
          :model-value="modelValue"
          key-button
          data-testid="ai-model"
          @update:model-value="chooseModel"
        />
      </AppSection>
      <AppSection
        divided
        gutter
      >
        <h3>Confirmations</h3>
        <AppToggle
          :model-value="allowAll"
          label="Allow all changes in every chat"
          data-testid="ai-allow-all"
          @update:model-value="setAllowAll"
        />
      </AppSection>
      <AppSection
        divided
        gutter
      >
        <h3>Archive</h3>
        <AppSpinner v-if="archive.isPending.value" />
        <AppBanner
          v-else-if="archive.isError.value"
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
          <div
            v-for="chat in archived"
            :key="chat.id"
            class="ai-archived"
            :data-testid="`ai-archived-${chat.id}`"
          >
            <span
              class="ai-archived__title"
              :title="chat.title"
            >{{ chat.title }}</span>
            <AppIconButton
              icon="unarchive"
              tooltip="Restore chat"
              compact
              :data-testid="`ai-restore-${chat.id}`"
              @click="restore(chat.id)"
            />
            <AppIconButton
              icon="delete"
              tooltip="Delete chat"
              variant="danger-quiet"
              compact
              :data-testid="`ai-delete-${chat.id}`"
              @click="remove(chat.id, chat.title)"
            />
          </div>
          <AppButton
            variant="danger-quiet"
            size="sm"
            label="Delete all"
            data-testid="ai-delete-all"
            @click="removeAll"
          />
        </template>
      </AppSection>
    </template>
  </div>
</template>

<style scoped>
.ai-settings { height: 100%; overflow: auto; }
.ai-settings h2, .ai-settings h3 { margin: 0; font-size: 16px; font-weight: 500; }
.ai-settings h3 { font-size: 14px; }
.ai-archived { display: flex; align-items: center; gap: var(--dp-space-1); }
.ai-archived__title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
