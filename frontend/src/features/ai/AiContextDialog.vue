<script setup lang="ts">
import { ref, watch } from "vue"

import type { ScreenContext } from "@/client"
import { AppButton, AppCheckbox } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  contexts: ScreenContext[]
  selected: string[]
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  apply: [panelIds: string[]]
}>()

const draft = ref<string[]>([])
watch(() => props.modelValue, (shown) => {
  if (shown) draft.value = [...props.selected]
})

function toggle(panelId: string, checked: boolean) {
  if (checked) {
    if (!draft.value.includes(panelId) && draft.value.length < 5) draft.value = [...draft.value, panelId]
  } else {
    draft.value = draft.value.filter((id) => id !== panelId)
  }
}

function apply() {
  emit("apply", draft.value)
  emit("update:modelValue", false)
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Attach workspace tabs"
    subtitle="Choose up to five tabs for the next message only."
    size="md"
    icon="attach_file"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div
      v-if="contexts.length"
      class="ai-context-dialog__list"
    >
      <AppCheckbox
        v-for="context in contexts"
        :key="context.panel_id"
        :model-value="draft.includes(context.panel_id)"
        :label="context.label"
        :dense="true"
        @update:model-value="toggle(context.panel_id, $event)"
      />
    </div>
    <div
      v-else
      class="ai-context-dialog__empty"
    >
      There are no attachable workspace tabs.
    </div>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Done"
        @click="apply"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.ai-context-dialog__list { display: grid; gap: var(--dp-space-2); min-width: 360px; }
.ai-context-dialog__empty { color: var(--dp-text-muted); }
</style>
