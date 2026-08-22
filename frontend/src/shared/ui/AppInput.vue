<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: string | number | null
    label?: string
    type?: "text" | "password" | "number" | "email"
    /** The message, not a boolean: an empty string means no error. */
    error?: string
    placeholder?: string
    disable?: boolean
  }>(),
  { label: undefined, type: "text", error: "", placeholder: undefined, disable: false }
)

const emit = defineEmits<{ "update:modelValue": [value: string | number | null] }>()
</script>

<template>
  <q-input
    :model-value="modelValue"
    :label="label"
    :type="type"
    :placeholder="placeholder"
    :disable="disable"
    :error="Boolean(error)"
    :error-message="error"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
