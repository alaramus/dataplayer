<script setup lang="ts">
import { ref, watch } from "vue"

import { AppBanner, AppButton, AppInput, AppForm } from "@/shared/ui"
import { t } from "@/shared/i18n"
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
    sizing="stable"
    size="compact-form"
    :title="t('structure.default_dialog.title', { name })"
    data-testid="structure-default-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-default-error"
      >
        {{ error }}
      </AppBanner>
      <div v-if="currentDefault !== null">
        {{ t('structure.default_dialog.current') }} <code>{{ currentDefault }}</code>
      </div>
      <AppInput
        :model-value="value"
        :label="t('structure.default_dialog.value')"
        :hint="t('structure.default_dialog.hint')"
        :disable="saving"
        data-testid="structure-default-value"
        @update:model-value="value = $event"
      />
    </AppForm>
    <template #actions>
      <AppButton
        v-if="currentDefault !== null"
        :label="t('structure.default_dialog.drop')"
        variant="danger-quiet"
        :disable="saving"
        data-testid="structure-default-drop"
        @click="emit('drop')"
      />
      <AppButton
        :label="t('catalog.common.cancel')"
        variant="quiet"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="t('structure.default_dialog.set')"
        :loading="saving"
        data-testid="structure-default-save"
        @click="emit('save', value)"
      />
    </template>
  </WindowDialog>
</template>
