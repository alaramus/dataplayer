<script setup lang="ts">
import AppInput from "@/shared/ui/AppInput.vue"
import AppNumberInput from "@/shared/ui/AppNumberInput.vue"
import AppSelect from "@/shared/ui/AppSelect.vue"
import AppToggle from "@/shared/ui/AppToggle.vue"

import type { FieldSpec } from "./jsonSchema"

const props = defineProps<{
  fields: FieldSpec[]
  modelValue: Record<string, unknown>
  errors: Record<string, string>
  secretPlaceholder?: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: Record<string, unknown>]
}>()

function update(name: string, value: unknown) {
  emit("update:modelValue", { ...props.modelValue, [name]: value })
}

function textValue(name: string): string {
  const value = props.modelValue[name]
  return value === null || value === undefined ? "" : String(value)
}

function numberValue(name: string): number | null {
  const value = props.modelValue[name]
  return typeof value === "number" ? value : null
}
</script>

<template>
  <div class="q-gutter-md">
    <template
      v-for="field in fields"
      :key="field.name"
    >
      <AppToggle
        v-if="field.kind === 'boolean'"
        :data-testid="`field-${field.name}`"
        :model-value="Boolean(modelValue[field.name])"
        :label="field.label"
        @update:model-value="update(field.name, $event)"
      />

      <!-- choices is optional on FieldSpec, and the untyped q-select used to
           accept undefined without a word. -->
      <AppSelect
        v-else-if="field.kind === 'select'"
        :data-testid="`field-${field.name}`"
        :model-value="modelValue[field.name]"
        :options="field.choices ?? []"
        :label="field.label"
        :error="errors[field.name]"
        @update:model-value="update(field.name, $event)"
      />

      <!-- A number reports a number and an emptied field reports null, so no
           screen has to coerce what the control gives back. -->
      <AppNumberInput
        v-else-if="field.kind === 'number'"
        :data-testid="`field-${field.name}`"
        :model-value="numberValue(field.name)"
        :label="field.label"
        :error="errors[field.name]"
        @update:model-value="update(field.name, $event)"
      />

      <AppInput
        v-else
        :data-testid="`field-${field.name}`"
        :model-value="textValue(field.name)"
        :label="field.label"
        :type="field.kind === 'password' ? 'password' : 'text'"
        :placeholder="field.kind === 'password' ? secretPlaceholder : undefined"
        :error="errors[field.name]"
        @update:model-value="update(field.name, $event)"
      />
    </template>
  </div>
</template>
