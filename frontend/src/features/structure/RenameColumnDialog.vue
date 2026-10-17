<script setup lang="ts">
import { ref, watch } from "vue"

import { AppBanner, AppButton, AppInput, AppForm } from "@/shared/ui"
import { t } from "@/shared/i18n"
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
    sizing="stable"
    size="compact-form"
    :title="t('structure.rename_dialog.title', { name })"
    data-testid="structure-rename-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-rename-error"
      >
        {{ error }}
      </AppBanner>
      <AppInput
        :model-value="newName"
        :label="t('structure.rename_dialog.new_name')"
        :disable="saving"
        data-testid="structure-rename-new-name"
        @update:model-value="newName = $event"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="t('structure.rename_dialog.rename')"
        :disable="newName.length === 0 || newName === name"
        :loading="saving"
        data-testid="structure-rename-save"
        @click="emit('save', newName)"
      />
    </template>
  </WindowDialog>
</template>
