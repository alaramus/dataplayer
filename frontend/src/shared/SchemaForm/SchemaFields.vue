<script setup lang="ts">
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

function inputType(kind: FieldSpec["kind"]): "password" | "number" | "text" {
  if (kind === "password") return "password"
  if (kind === "number") return "number"
  return "text"
}

// The cast lives here rather than in the template: the Vue parser mistakes the
// union-type pipe for a deprecated filter.
function inputValue(name: string): string | number | null {
  return (props.modelValue[name] ?? null) as string | number | null
}
</script>

<template>
  <div class="q-gutter-md">
    <template
      v-for="field in fields"
      :key="field.name"
    >
      <q-toggle
        v-if="field.kind === 'boolean'"
        :data-testid="`field-${field.name}`"
        :model-value="Boolean(modelValue[field.name])"
        :label="field.label"
        @update:model-value="update(field.name, $event)"
      />

      <q-select
        v-else-if="field.kind === 'select'"
        :data-testid="`field-${field.name}`"
        :model-value="modelValue[field.name]"
        :options="field.choices"
        :label="field.label"
        :error="Boolean(errors[field.name])"
        :error-message="errors[field.name]"
        @update:model-value="update(field.name, $event)"
      />

      <q-input
        v-else
        :data-testid="`field-${field.name}`"
        :model-value="inputValue(field.name)"
        :label="field.label"
        :type="inputType(field.kind)"
        :placeholder="field.kind === 'password' ? secretPlaceholder : undefined"
        :error="Boolean(errors[field.name])"
        :error-message="errors[field.name]"
        @update:model-value="update(field.name, field.kind === 'number' ? Number($event) : $event)"
      />
    </template>
  </div>
</template>
