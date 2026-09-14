<script setup lang="ts">
import { computed, ref } from "vue"

import { AppBanner, AppIconButton, AppSection, AppSelect, AppSpinner, AppToggle, useToast } from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import AiKeyDialog from "./AiKeyDialog.vue"
import { useAiModels, useAiSettings, useUpdateAiSettings } from "./api"
import { groupedModelOptions, providers } from "./modelOptions"
import type { ModelOption, Provider } from "./modelOptions"

const settings = useAiSettings()
const models = useAiModels()
const update = useUpdateAiSettings()
const toast = useToast()
const keyProvider = ref<Provider | null>(null)
const keyDialogOpen = ref(false)
const keySet = (provider: Provider) => settings.data.value?.keys.find((one) => one.provider === provider)?.set ?? false

const modelOptions = computed<ModelOption[]>(() => groupedModelOptions(
  models.data.value ?? [], settings.data.value?.keys ?? []
))
const modelValue = computed(() => settings.data.value?.model_key ?? null)
const allowAll = computed(() => settings.data.value?.allow_all_changes ?? false)
const selectedModel = computed(() => (models.data.value ?? []).find((one) => one.key === modelValue.value) ?? null)
const selectedKeySet = computed(() => selectedModel.value ? keySet(selectedModel.value.provider) : false)
const selectedProvider = computed(() => providers.find((one) => one.id === keyProvider.value) ?? null)

function manageKey(provider: Provider) { keyProvider.value = provider; keyDialogOpen.value = true }
function manageOptionKey(option: SelectOption) {
  const provider = (option as ModelOption).provider
  if (provider) manageKey(provider)
}
function manageSelectedKey() {
  if (selectedModel.value) manageKey(selectedModel.value.provider)
}
async function chooseModel(value: unknown) {
  try { await update.mutateAsync({ model_key: typeof value === "string" ? value : null }) }
  catch (cause) { toast.error(messageOf(cause, "The model could not be selected")) }
}
async function setAllowAll(value: boolean) {
  try { await update.mutateAsync({ allow_all_changes: value }) }
  catch (cause) { toast.error(messageOf(cause, "The confirmation setting could not be changed")) }
}
</script>

<template>
  <div class="ai-settings" data-testid="ai-settings">
    <h2>Settings</h2>
    <AppSpinner v-if="settings.isPending.value || models.isPending.value" />
    <AppBanner v-else-if="settings.isError.value || models.isError.value" tone="error">Agent settings could not be loaded.</AppBanner>
    <template v-else>
      <AppSection gutter>
        <h3>Model</h3>
        <AppBanner v-if="settings.data.value?.model_missing" tone="warning">The saved model is no longer available. Choose another one.</AppBanner>
        <AppSelect
          :model-value="modelValue"
          :options="modelOptions"
          label="Model"
          data-testid="ai-model"
          @update:model-value="chooseModel"
          @option-action="manageOptionKey"
        >
          <template #after>
            <AppIconButton
              :icon="selectedKeySet ? 'key' : 'key_off'"
              :active="selectedKeySet"
              tooltip="Manage the selected model provider key"
              :disable="modelValue === null"
              data-testid="ai-selected-model-key"
              @click="manageSelectedKey"
            />
          </template>
        </AppSelect>
      </AppSection>
      <AppSection divided gutter>
        <h3>Confirmations</h3>
        <AppToggle :model-value="allowAll" label="Allow all changes in every chat" data-testid="ai-allow-all" @update:model-value="setAllowAll" />
      </AppSection>
    </template>
    <AiKeyDialog
      v-if="selectedProvider"
      v-model="keyDialogOpen"
      :provider="selectedProvider.id"
      :provider-label="selectedProvider.label"
      :key-set="keySet(selectedProvider.id)"
    />
  </div>
</template>

<style scoped>
.ai-settings { height: 100%; overflow: auto; }
.ai-settings h2, .ai-settings h3 { margin: 0; font-size: 16px; font-weight: 500; }
.ai-settings h3 { font-size: 14px; }
</style>
