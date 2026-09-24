<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import { AppBanner, AppButton, AppEmptyState, AppForm, AppIconButton, AppSpinner, AppToggle, useConfirm, useToast } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import AiModelSelect from "./AiModelSelect.vue"
import AiKeyDialog from "./AiKeyDialog.vue"
import {
  useAiSettings,
  useAiModels,
  useArchivedAiConversations,
  useDeleteAiConversation,
  useDeleteArchivedAiConversations,
  useUpdateAiConversation,
  useUpdateAiSettings,
} from "./api"
import { autoModelValue, fallbackModel } from "./modelOptions"

const settings = useAiSettings()
const models = useAiModels()
const update = useUpdateAiSettings()
const archive = useArchivedAiConversations()
const updateConversation = useUpdateAiConversation()
const deleteConversation = useDeleteAiConversation()
const deleteArchived = useDeleteArchivedAiConversations()
const confirm = useConfirm()
const toast = useToast()
const modelValue = computed(() => settings.data.value?.auto_provider
  ? autoModelValue(settings.data.value.auto_provider)
  : settings.data.value?.model_key ?? null)
const allowAll = computed(() => settings.data.value?.allow_all_changes ?? false)
const jevKeySet = computed(() => settings.data.value?.keys.some((key) => key.provider === "typesafe" && key.set) ?? false)
const jevDialogOpen = ref(false)
const archived = computed(() => archive.data.value?.data ?? [])

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
            data-testid="ai-model"
            @update:model-value="chooseModel"
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
          <div class="ai-settings__archived-list">
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
                :icon="appIcons.unarchive"
                tooltip="Restore chat"
                compact
                :data-testid="`ai-restore-${chat.id}`"
                @click="restore(chat.id)"
              />
              <AppIconButton
                :icon="appIcons.delete"
                tooltip="Delete chat"
                variant="danger-quiet"
                compact
                :data-testid="`ai-delete-${chat.id}`"
                @click="remove(chat.id, chat.title)"
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
.ai-settings h3 { margin: 0; font-size: 14px; font-weight: 600; }
.ai-settings__group { border-bottom: 1px solid var(--dp-border-faint); }
.ai-settings__form { max-width: 640px; }
.ai-settings__archive { display: flex; flex-direction: column; gap: var(--dp-space-3); max-width: 640px; padding: var(--dp-space-4); }
.ai-settings__archived-list { display: flex; flex-direction: column; }
.ai-settings__delete-all { align-self: flex-start; }
.ai-archived { display: flex; align-items: center; gap: var(--dp-space-1); min-width: 0; padding: var(--dp-space-2) 0; }
.ai-archived + .ai-archived { border-top: 1px solid var(--dp-border-faint); }
.ai-archived__title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
