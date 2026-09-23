<script setup lang="ts">
import { AppButton, AppForm, AppInput } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/** Naming a tab group: the same window for saving one and renaming one. */
defineProps<{
  modelValue: boolean
  title: string
  /** What is wrong with the name, or an empty string. */
  problem: string
  busy: boolean
}>()
const name = defineModel<string>("name", { required: true })
const emit = defineEmits<{ "update:modelValue": [open: boolean]; confirm: [] }>()
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="title"
    size="sm"
    sizing="stable"
    data-testid="tab-group-name-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppInput
        v-model="name"
        label="Group name"
        :error="name.length > 0 ? problem : ''"
        autofocus
        maxlength="80"
        data-testid="tab-group-name"
        @keydown.enter.prevent="emit('confirm')"
      />
    </AppForm>
    <template #actions>
      <AppButton variant="quiet" label="Cancel" @click="emit('update:modelValue', false)" />
      <AppButton
        label="Save"
        :disable="Boolean(problem) || busy"
        data-testid="confirm-tab-group-name"
        @click="emit('confirm')"
      />
    </template>
  </WindowDialog>
</template>
