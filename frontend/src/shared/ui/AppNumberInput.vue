<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: number | null
    label?: string
    error?: string
    disable?: boolean
  }>(),
  { label: undefined, error: "", disable: false }
)

const emit = defineEmits<{ "update:modelValue": [value: number | null] }>()

/**
 * Separate from AppInput because the two report different things, and one
 * component reporting `string | number | null` would push that union onto
 * every caller's own state.
 *
 * An emptied field is null rather than 0: a port nobody filled in is missing,
 * not zero.
 */
function report(value: string | number | null) {
  emit("update:modelValue", value === null || value === "" ? null : Number(value))
}
</script>

<template>
  <q-input
    type="number"
    :model-value="modelValue"
    :label="label"
    :disable="disable"
    :error="Boolean(error)"
    :error-message="error"
    @update:model-value="report"
  >
    <template
      v-if="$slots.after"
      #after
    >
      <slot name="after" />
    </template>
  </q-input>
</template>
