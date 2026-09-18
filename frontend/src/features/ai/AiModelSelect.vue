<script setup lang="ts">
import { computed, ref } from "vue"

import { AppIconButton, AppSelect } from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"

import AiKeyDialog from "./AiKeyDialog.vue"
import { useAiModels, useAiSettings } from "./api"
import { groupedModelOptions, providers } from "./modelOptions"
import type { ModelOption, Provider } from "./modelOptions"

/**
 * Choosing a model, and the provider key that makes it usable.
 *
 * The two belong together wherever a model is chosen: a row that says "API key
 * required" and cannot be acted on is a dead end, and the settings and the
 * composer would otherwise each carry their own copy of the key window.
 *
 * Trap: this must stay a single root element — a field beside a dialog is a
 * fragment, the caller's class and scoped styles then reach nothing, and the
 * field collapsed to no width in the composer's row. That includes not putting
 * a comment beside the root, which makes a fragment of it in a development
 * build. The key window floats, so it takes no room inside the wrapper.
 */
const props = withDefaults(
  defineProps<{
    modelValue: string | null
    compact?: boolean
    disable?: boolean
    /** Also offer the key of the model that is chosen, beside the field. */
    keyButton?: boolean
  }>(),
  { compact: false, disable: false, keyButton: false }
)
const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const models = useAiModels()
const settings = useAiSettings()
const keyProvider = ref<Provider | null>(null)
const keyDialogOpen = ref(false)

const keySet = (provider: Provider) =>
  settings.data.value?.keys.find((one) => one.provider === provider)?.set ?? false
const options = computed<ModelOption[]>(() =>
  groupedModelOptions(models.data.value ?? [], settings.data.value?.keys ?? [])
)
const selectedModel = computed(
  () => (models.data.value ?? []).find((one) => one.key === props.modelValue) ?? null
)
const selectedKeySet = computed(() =>
  selectedModel.value ? keySet(selectedModel.value.provider) : false
)
const dialogProvider = computed(
  () => providers.find((one) => one.id === keyProvider.value) ?? null
)

function manageKey(provider: Provider) {
  keyProvider.value = provider
  keyDialogOpen.value = true
}
function manageOptionKey(option: SelectOption) {
  const provider = (option as ModelOption).provider
  if (provider) manageKey(provider)
}
function manageSelectedKey() {
  if (selectedModel.value) manageKey(selectedModel.value.provider)
}
function choose(value: unknown) {
  if (typeof value === "string") emit("update:modelValue", value)
}
</script>

<template>
  <span class="ai-model-select">
    <AppSelect
      :model-value="modelValue"
      :options="options"
      :compact="compact"
      :disable="disable"
      :loading="models.isPending.value"
      label="Model"
      @update:model-value="choose"
      @option-action="manageOptionKey"
    >
      <template
        v-if="keyButton"
        #after
      >
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
    <AiKeyDialog
      v-if="dialogProvider"
      v-model="keyDialogOpen"
      :provider="dialogProvider.id"
      :provider-label="dialogProvider.label"
      :key-set="keySet(dialogProvider.id)"
    />
  </span>
</template>

<style scoped>
.ai-model-select { display: flex; min-width: 0; }
.ai-model-select .q-field { flex: 1; min-width: 0; }
</style>
