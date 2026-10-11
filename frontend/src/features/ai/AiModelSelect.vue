<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { AppIconButton, AppSelect, appIcons, useConfirm, useToast } from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { serverStorageKey } from "@/shared/servers/context"

import AiKeyDialog from "./AiKeyDialog.vue"
import AiModelHint from "./AiModelHint.vue"
import { useAiModels, useAiSettings } from "./api"
import { browserModelOptions, useBrowserModel } from "./browserModel"
import { AUTO_ALL_VALUE, JEV_PROVIDER, groupedModelOptions, jevProviderLabel, providerLabel } from "./modelOptions"
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
    /** Plain chat chooses a concrete model and does not route through Jev. */
    allowAuto?: boolean
    /**
     * Point at the field while no model is chosen. Off where choosing is the
     * screen itself, as in AI settings: there is nothing to point at.
     */
    hint?: boolean
    /** A read of the caller's that may still name the model, such as its chat. */
    pending?: boolean
    /** Also offer the model Chrome runs on this computer (D223). */
    browserModel?: boolean
  }>(),
  { compact: false, disable: false, keyButton: false, allowAuto: true, hint: true, pending: false, browserModel: false }
)
const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const models = useAiModels()
const settings = useAiSettings()
const me = useCurrentUser()
const confirm = useConfirm()
const toast = useToast()
const keyProvider = ref<Provider | null>(null)
const keyDialogOpen = ref(false)
/**
 * The hint opens over the field while no model is chosen and the reads that
 * could name one have landed. Dismissed until a model arrives: choosing one
 * re-arms it through the value going back to nothing.
 */
const hintDismissed = ref(false)
const hintOpen = ref(false)

const keySet = (provider: Provider) =>
  settings.data.value?.keys.find((one) => one.provider === provider)?.set ?? false
const browser = useBrowserModel()
watch(() => props.browserModel, (offered) => { if (offered) void browser.refresh() }, { immediate: true })
const options = computed<ModelOption[]>(() => [
  ...groupedModelOptions(models.data.value ?? [], settings.data.value?.keys ?? [])
    .filter((option) => props.allowAuto || !option.auto),
  ...(props.browserModel ? browserModelOptions(browser.state.value) : []),
])
const selectedModel = computed(
  () => (models.data.value ?? []).find((one) => one.key === props.modelValue) ?? null
)
const selectedProvider = computed(() => selectedModel.value?.provider
  ?? (models.data.value ?? []).find((model) => props.modelValue === `auto:${model.provider}`)?.provider
  ?? null)
const selectedKeySet = computed(() =>
  selectedProvider.value ? keySet(selectedProvider.value) : false
)
const dialogProvider = computed(() => keyProvider.value === null
  ? null
  : {
    id: keyProvider.value,
    label: keyProvider.value === JEV_PROVIDER
      ? jevProviderLabel
      : providerLabel(models.data.value ?? [], keyProvider.value),
  })
watch(
  [
    () => props.modelValue,
    () => models.isPending.value || settings.isPending.value || props.pending,
  ] as const,
  ([value, pending]) => {
    if (value !== null) {
      hintDismissed.value = false
      hintOpen.value = false
      return
    }
    if (props.hint && !pending && !hintDismissed.value) hintOpen.value = true
  },
  { immediate: true }
)
/** A close from the popup itself dismisses it; the watcher above owns the rest. */
function noteHintClosed(value: boolean) {
  if (!value) hintDismissed.value = true
}
/**
 * The field itself is inside the popup's anchor, so a press on it does not
 * count as outside: reaching for the list dismisses the hint explicitly,
 * or the two stand open one over the other.
 */
function dismissHint() {
  hintOpen.value = false
  hintDismissed.value = true
}

function manageKey(provider: Provider) {
  keyProvider.value = provider
  keyDialogOpen.value = true
}
function manageOptionKey(option: SelectOption) {
  const target = (option as ModelOption).keyProvider ?? (option as ModelOption).provider
  if (target) manageKey(target)
}
function manageSelectedKey() {
  if (selectedProvider.value) manageKey(selectedProvider.value)
}
async function choose(value: unknown) {
  if (typeof value !== "string" || value === props.modelValue) return
  const option = options.value.find((one) => one.value === value)
  // A heading is an enabled row (its key button must stay pressable) but
  // never a value: the keyboard can still land on one.
  if (option?.disable || option?.group) return
  if (option?.auto) {
    const isAll = value === AUTO_ALL_VALUE
    const provider = option.provider
    if (!isAll && !provider) return
    const userId = me.data.value?.id
    const warningKey = userId ? serverStorageKey(`dataplayer-ai-jev-routing:skip-warning:${userId}`) : null
    let skipWarning = false
    if (warningKey) {
      try { skipWarning = localStorage.getItem(warningKey) === "true" } catch { /* Ask when unavailable. */ }
    }
    if (!skipWarning && !(await confirm({
      title: "Let Jev choose the model?",
      message: isAll || !provider
        ? "Jev will choose from every model with a configured API key for each answer. Models may differ in cost and capabilities. Your request will be sent to TypeSafe to make the choice."
        : `Jev will choose from every ${providerLabel(models.data.value ?? [], provider)} model for each answer. Models may differ in cost and capabilities. Your request will be sent to TypeSafe to make the choice.`,
      confirmLabel: "Use Jev",
      rememberLabel: "Don't show again",
      onRemember: () => {
        if (!warningKey) return
        try { localStorage.setItem(warningKey, "true") }
        catch { toast.error("The browser could not remember this preference.") }
      },
    }))) return
  }
  emit("update:modelValue", value)
}
</script>

<template>
  <span
    class="ai-model-select"
    @pointerdown="dismissHint"
    @focusin="dismissHint"
  >
    <AppSelect
      :model-value="modelValue"
      :options="options"
      :compact="compact"
      :disable="disable"
      :loading="models.isPending.value"
      label="Model"
      :label-hidden="compact"
      :framed="compact"
      placeholder="Choose a model"
      @update:model-value="choose"
      @option-action="manageOptionKey"
    >
      <template
        v-if="keyButton"
        #after
      >
        <AppIconButton
          :icon="selectedKeySet ? appIcons.key : appIcons.keyOff"
          :active="selectedKeySet"
          tooltip="Manage the selected model provider key"
          :disable="selectedProvider === null"
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
    <!-- Inside the root, so the popup anchors to this field. The trap in the
         header comment holds for it too: it takes no room in the wrapper. -->
    <AiModelHint
      v-model="hintOpen"
      @update:model-value="noteHintClosed"
    />
  </span>
</template>

<style scoped>
.ai-model-select { display: flex; min-width: 0; }
.ai-model-select .q-field { flex: 1; min-width: 0; }
</style>
