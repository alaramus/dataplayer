<script setup lang="ts">
import { copyText } from "@/shared/clipboard"
import { t } from "@/shared/i18n"
import { AppButton, AppCopyButton, useToast } from "@/shared/ui"
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
    toast.error(t("grid.cell_viewer.copy_failed"))
  }
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="`${columnName} — ${typeSql}`"
    size="lg"
    sizing="stable"
    data-testid="grid-viewer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="cell-value-dialog">
      <pre class="cell-value-dialog__value">{{ value }}</pre>
    </div>
    <template #actions>
      <AppCopyButton
        :tooltip="t('grid.cell_viewer.copy')"
        data-testid="grid-viewer-copy"
        @click="copyValue"
      />
      <AppButton
        :label="t('catalog.common.close')"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.cell-value-dialog {
  padding: var(--dp-space-4);
}
.cell-value-dialog__value {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
