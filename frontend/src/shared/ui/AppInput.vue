<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: string
    label?: string
    type?: "text" | "password" | "email"
    /** The message, not a boolean: an empty string means no error. */
    error?: string
    placeholder?: string
    disable?: boolean
    /** A field in a toolbar rather than in a form: tighter, and no underline. */
    compact?: boolean
  }>(),
  {
    label: undefined,
    type: "text",
    error: "",
    placeholder: undefined,
    disable: false,
    compact: false,
  }
)

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

// QInput reports string | number | null whatever its type is. A text field
// deals in strings, so the caller is not made to widen its own state to match
// a detail of the library. Numbers have their own component.
function report(value: string | number | null) {
  emit("update:modelValue", value === null ? "" : String(value))
}
</script>

<template>
  <q-input
    :model-value="modelValue"
    :label="label"
    :type="type"
    :placeholder="placeholder"
    :dense="compact"
    :borderless="compact"
    :disable="disable"
    :error="Boolean(error)"
    :error-message="error"
    @update:model-value="report"
  />
</template>
