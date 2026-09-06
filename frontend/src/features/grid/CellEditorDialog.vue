<script setup lang="ts">
import { ref, watch } from "vue"

import type { FetchColumn } from "@/client"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppInput,
  AppSection,
  AppSelect,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  column: FetchColumn
  value: string | null
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [value: string | null]
}>()

const draft = ref("")
const isNull = ref(false)

watch(
  () => [props.value, props.modelValue] as const,
  ([value]) => {
    draft.value = value ?? ""
    isNull.value = value === null
  },
  { immediate: true }
)

function save() {
  emit("save", isNull.value ? null : draft.value)
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="`Edit ${column.name} — ${column.type.sql}`"
    data-testid="grid-cell-editor"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="grid-edit-error"
      >
        {{ error }}
      </AppBanner>
      <AppCheckbox
        v-if="column.nullable === true"
        :model-value="isNull"
        label="Set SQL NULL"
        data-testid="grid-edit-null"
        @update:model-value="isNull = $event"
      />
      <AppSelect
        v-if="column.type.category === 'boolean'"
        :model-value="draft"
        :options="[
          { label: 'True', value: 'true' },
          { label: 'False', value: 'false' },
        ]"
        label="Value"
        :disable="isNull || saving"
        data-testid="grid-edit-value"
        @update:model-value="draft = String($event)"
      />
      <AppInput
        v-else
        :model-value="draft"
        label="Value"
        :disable="isNull || saving"
        data-testid="grid-edit-value"
        @update:model-value="draft = $event"
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
        variant="primary"
        label="Save"
        :loading="saving"
        data-testid="grid-edit-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>
