<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: number | null
    label?: string
    error?: string
    /**
     * The line under the field, in the source's own words: what to write, or
     * what leaving it empty means. Not an error and not a placeholder — it is
     * there whether or not the field is filled.
     */
    hint?: string
    disable?: boolean
  }>(),
  { label: undefined, error: "", hint: undefined, disable: false }
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
    :hint="hint"
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
