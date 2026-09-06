<script setup lang="ts">
import { ref, watch } from "vue"

import { AppBanner, AppButton, AppInput, AppSection } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  name: string
  currentDefault: string | null
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [value: string]
  drop: []
}>()
const value = ref("")

watch(
  () => props.modelValue,
  (open) => {
    if (open) value.value = ""
  },
  { immediate: true }
)
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="`Column default — ${name}`"
    data-testid="structure-default-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-default-error"
      >
        {{ error }}
      </AppBanner>
      <div v-if="currentDefault !== null">
        Current source expression: <code>{{ currentDefault }}</code>
      </div>
      <AppInput
        :model-value="value"
        label="New literal value"
        hint="Saved as a value, never executed as SQL. An empty box sets the empty string."
        :disable="saving"
        data-testid="structure-default-value"
        @update:model-value="value = $event"
      />
    </AppSection>
    <template #actions>
      <AppButton
        v-if="currentDefault !== null"
        label="Drop default"
        variant="danger-quiet"
        :disable="saving"
        data-testid="structure-default-drop"
        @click="emit('drop')"
      />
      <AppButton
        label="Cancel"
        variant="secondary"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Set default"
        :loading="saving"
        data-testid="structure-default-save"
        @click="emit('save', value)"
      />
    </template>
  </WindowDialog>
</template>
