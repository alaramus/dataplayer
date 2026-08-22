<script setup lang="ts">
import { computed } from "vue"

export interface SelectOption {
  label: string
  value: string | number
}

const props = withDefaults(
  defineProps<{
    modelValue: unknown
    options: readonly (string | SelectOption)[]
    label?: string
    error?: string
    loading?: boolean
    disable?: boolean
  }>(),
  { label: undefined, error: "", loading: false, disable: false }
)

const emit = defineEmits<{ "update:modelValue": [value: unknown] }>()

// A caller passes either plain strings or {label, value} pairs, and the four
// Quasar props that distinguish them are derived here rather than repeated at
// every call site.
const labelled = computed(() => props.options.some((option) => typeof option === "object"))
</script>

<template>
  <q-select
    :model-value="modelValue"
    :options="options"
    :label="label"
    :option-value="labelled ? 'value' : undefined"
    :option-label="labelled ? 'label' : undefined"
    :emit-value="labelled"
    :map-options="labelled"
    :loading="loading"
    :disable="disable"
    :error="Boolean(error)"
    :error-message="error"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
