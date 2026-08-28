<script setup lang="ts">
import { ref, watch } from "vue"

import type { ColumnTypeOption } from "@/client"
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
  types: ColumnTypeOption[]
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [value: { name: string; typeCode: string; nullable: boolean }]
}>()

const name = ref("")
const typeCode = ref("")
const nullable = ref(true)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    name.value = ""
    typeCode.value = props.types[0]?.code ?? ""
    nullable.value = true
  },
  { immediate: true }
)

function save() {
  emit("save", { name: name.value, typeCode: typeCode.value, nullable: nullable.value })
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Add column"
    subtitle="The source controls the available SQL types"
    data-testid="structure-add-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-add-error"
      >
        {{ error }}
      </AppBanner>
      <AppInput
        :model-value="name"
        label="Column name"
        :disable="saving"
        data-testid="structure-add-name"
        @update:model-value="name = $event"
      />
      <AppSelect
        :model-value="typeCode"
        :options="types.map((type) => ({ label: `${type.title} · ${type.sql}`, value: type.code }))"
        label="Type"
        :disable="saving"
        data-testid="structure-add-type"
        @update:model-value="typeCode = String($event)"
      />
      <AppCheckbox
        :model-value="nullable"
        label="Allow SQL NULL"
        :disable="saving"
        data-testid="structure-add-nullable"
        @update:model-value="nullable = $event"
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
        label="Add"
        :disable="name.length === 0 || typeCode.length === 0"
        :loading="saving"
        data-testid="structure-add-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>
