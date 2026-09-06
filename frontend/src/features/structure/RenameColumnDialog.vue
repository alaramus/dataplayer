<script setup lang="ts">
import { ref, watch } from "vue"

import { AppBanner, AppButton, AppInput, AppSection } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  name: string
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [newName: string]
}>()
const newName = ref("")

watch(
  () => [props.modelValue, props.name] as const,
  ([open, name]) => {
    if (open) newName.value = name
  },
  { immediate: true }
)
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="`Rename column — ${name}`"
    data-testid="structure-rename-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-rename-error"
      >
        {{ error }}
      </AppBanner>
      <AppInput
        :model-value="newName"
        label="New column name"
        :disable="saving"
        data-testid="structure-rename-new-name"
        @update:model-value="newName = $event"
      />
    </AppSection>
    <template #actions>
      <AppButton
        variant="secondary"
        label="Cancel"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Rename"
        :disable="newName.length === 0 || newName === name"
        :loading="saving"
        data-testid="structure-rename-save"
        @click="emit('save', newName)"
      />
    </template>
  </WindowDialog>
</template>
