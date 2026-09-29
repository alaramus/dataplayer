<script setup lang="ts">
import { ref, watch } from "vue"

import type { FetchColumn } from "@/client"
import {
  AppButton,
  AppCheckbox,
  AppForm,
  AppInput,
  AppSelect,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { inputHint } from "./model"

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
    :title="`Edit ${column.name}`"
    size="compact-form"
    sizing="stable"
    data-testid="grid-cell-editor"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <!-- What the source refused is said under the value it refused, as any
         field's error is, rather than in a banner above the whole form; and
         NULL, the alternative to a value, follows the value (D187). -->
    <AppForm layout="section">
      <AppSelect
        v-if="column.type.category === 'boolean'"
        :model-value="draft"
        :options="[
          { label: 'True', value: 'true' },
          { label: 'False', value: 'false' },
        ]"
        label="Value"
        :error="error"
        :disable="isNull || saving"
        data-testid="grid-edit-value"
        @update:model-value="draft = String($event)"
      />
      <AppInput
        v-else
        :model-value="draft"
        label="Value"
        :hint="`${column.type.sql} — ${inputHint(column.type)}`"
        :error="error"
        :disable="isNull || saving"
        data-testid="grid-edit-value"
        @update:model-value="draft = $event"
      />
      <AppCheckbox
        v-if="column.nullable === true"
        :model-value="isNull"
        label="Set SQL NULL"
        data-testid="grid-edit-null"
        @update:model-value="isNull = $event"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
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
