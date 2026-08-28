<script setup lang="ts">
import { copyText } from "@/shared/clipboard"
import { AppButton, AppCopyButton, AppSection, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

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
    await copyText(props.value)
  } catch {
    toast.error("Could not copy the value")
  }
}
</script>

<template>
  <WindowDialog
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
      <AppCopyButton
        tooltip="Copy the full value"
        data-testid="grid-viewer-copy"
        @click="copyValue"
      />
      <AppButton
        label="Close"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.cell-value-dialog__value {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
