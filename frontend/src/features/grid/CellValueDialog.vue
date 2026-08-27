<script setup lang="ts">
import { AppButton, AppDialog, AppSection, useToast } from "@/shared/ui"

import { writeSelection } from "./clipboard"

const props = defineProps<{
  modelValue: boolean
  columnName: string
  typeSql: string
  value: string
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
const toast = useToast()

async function copyValue() {
  try {
    await writeSelection(props.value)
  } catch {
    toast.error("Could not copy the value")
  }
}
</script>

<template>
  <AppDialog
    :model-value="modelValue"
    :title="columnName"
    :subtitle="typeSql"
    size="lg"
    data-testid="grid-viewer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection scroll>
      <pre class="cell-value-dialog__value">{{ value }}</pre>
    </AppSection>
    <template #actions>
      <AppButton
        variant="secondary"
        label="Copy"
        data-testid="grid-viewer-copy"
        @click="copyValue"
      />
      <AppButton
        label="Close"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </AppDialog>
</template>

<style scoped>
.cell-value-dialog__value {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
