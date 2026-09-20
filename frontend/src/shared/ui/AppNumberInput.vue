<script setup lang="ts">
import { inject } from "vue"

import { formLayoutKey } from "./formLayout"
import { fieldLook } from "./tokens"

const formLayout = inject(formLayoutKey, false)
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
    /** What a filled field looks like, shown while it is empty. */
    placeholder?: string
    disable?: boolean
  }>(),
  {
    label: undefined,
    error: "",
    hint: undefined,
    placeholder: undefined,
    disable: false,
  }
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
    :class="{ 'app-form-field': formLayout }"
    v-bind="fieldLook(formLayout)"
    type="number"
    :model-value="modelValue"
    :label="formLayout ? undefined : label"
    :aria-label="formLayout ? label : undefined"
    :hint="hint"
    :placeholder="placeholder"
    :stack-label="Boolean(placeholder)"
    :disable="disable"
    :error="Boolean(error)"
    :error-message="error"
    :aria-invalid="error ? 'true' : undefined"
    @update:model-value="report"
  >
    <template
      v-if="formLayout && label"
      #before
    >
      <span>{{ label }}</span>
    </template>
    <template
      v-if="$slots.after"
      #after
    >
      <slot name="after" />
    </template>
  </q-input>
</template>
