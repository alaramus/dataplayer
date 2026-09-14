<script setup lang="ts">
import { computed, reactive, ref } from "vue"

import type { ProviderKeyState } from "@/client"
import { AppBanner, AppButton, AppInput, AppSection, AppSelect, AppSpinner, AppToggle, useToast } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import { checkAiKey, useAiModels, useAiSettings, useRemoveAiKey, useUpdateAiSettings, useWriteAiKey } from "./api"

type Provider = ProviderKeyState["provider"]
const providers: { id: Provider; label: string }[] = [
  { id: "openai", label: "OpenAI" }, { id: "anthropic", label: "Anthropic" },
  { id: "deepseek", label: "DeepSeek" }, { id: "gemini", label: "Gemini" },
]
const settings = useAiSettings()
const models = useAiModels()
const update = useUpdateAiSettings()
const writeKey = useWriteAiKey()
const removeKey = useRemoveAiKey()
const toast = useToast()
const drafts = reactive<Record<Provider, string>>({ openai: "", anthropic: "", deepseek: "", gemini: "" })
const checking = ref<Provider | null>(null)

const modelOptions = computed(() => (models.data.value ?? []).map((model) => ({
  label: `${model.name} · ${providers.find((one) => one.id === model.provider)?.label ?? model.provider}`,
  value: model.key,
})))
const modelValue = computed(() => settings.data.value?.model_key ?? null)
const allowAll = computed(() => settings.data.value?.allow_all_changes ?? false)
const keySet = (provider: Provider) => settings.data.value?.keys.find((one) => one.provider === provider)?.set ?? false

async function saveKey(provider: Provider) {
  const key = drafts[provider].trim()
  if (!key) return
  try { await writeKey.mutateAsync({ provider, key }); drafts[provider] = ""; toast.success("Key saved") }
  catch (cause) { toast.error(messageOf(cause, "The key could not be saved")) }
}
async function check(provider: Provider) {
  checking.value = provider
  try { const result = await checkAiKey(provider); result.ok ? toast.success(result.message) : toast.error(result.message) }
  catch (cause) { toast.error(messageOf(cause, "The key could not be checked")) }
  finally { checking.value = null }
}
async function remove(provider: Provider) {
  try { await removeKey.mutateAsync(provider); toast.info("Key removed") }
  catch (cause) { toast.error(messageOf(cause, "The key could not be removed")) }
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
        <h3>Keys</h3>
        <div v-for="provider in providers" :key="provider.id" class="ai-settings__key">
          <AppInput v-model="drafts[provider.id]" type="password" :label="provider.label" :placeholder="keySet(provider.id) ? 'Key is set' : 'Paste a key'" :data-testid="`ai-key-${provider.id}`" @keyup.enter="saveKey(provider.id)" />
          <div class="ai-settings__key-actions">
            <AppButton size="sm" variant="quiet" label="Save" :disable="!drafts[provider.id].trim()" @click="saveKey(provider.id)" />
            <AppButton size="sm" variant="quiet" label="Check" :loading="checking === provider.id" :disable="!keySet(provider.id)" :data-testid="`ai-check-${provider.id}`" @click="check(provider.id)" />
            <AppButton v-if="keySet(provider.id)" size="sm" variant="danger-quiet" label="Remove" @click="remove(provider.id)" />
          </div>
        </div>
      </AppSection>
      <AppSection divided gutter>
        <h3>Model</h3>
        <AppBanner v-if="settings.data.value?.model_missing" tone="warning">The saved model is no longer available. Choose another one.</AppBanner>
        <AppSelect :model-value="modelValue" :options="modelOptions" label="Model" data-testid="ai-model" @update:model-value="chooseModel" />
      </AppSection>
      <AppSection divided gutter>
        <h3>Confirmations</h3>
        <AppToggle :model-value="allowAll" label="Allow all changes in every chat" data-testid="ai-allow-all" @update:model-value="setAllowAll" />
      </AppSection>
    </template>
  </div>
</template>

<style scoped>
.ai-settings { height: 100%; overflow: auto; }
.ai-settings h2, .ai-settings h3 { margin: 0; font-size: 16px; font-weight: 500; }
.ai-settings h3 { font-size: 14px; }
.ai-settings__key { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--dp-space-3); align-items: start; }
.ai-settings__key-actions { display: flex; gap: var(--dp-space-1); padding-top: var(--dp-space-2); }
</style>
