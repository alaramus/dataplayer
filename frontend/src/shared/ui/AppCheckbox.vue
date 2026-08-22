<script setup lang="ts">
/**
 * A tick box.
 *
 * Apart from AppToggle on purpose: a toggle turns a setting on, a checkbox
 * picks a thing out of a list, and the two are not interchangeable even though
 * both hold a boolean. `indeterminate` is what a "select all" box needs when
 * only some of the list is ticked.
 */
withDefaults(
  defineProps<{
    modelValue: boolean
    label?: string
    /** Some but not all: shown as a dash rather than a tick or an empty box. */
    indeterminate?: boolean
    dense?: boolean
  }>(),
  { label: undefined, indeterminate: false, dense: false }
)

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
</script>

<template>
  <q-checkbox
    :model-value="indeterminate ? null : modelValue"
    :toggle-indeterminate="false"
    :label="label"
    :dense="dense"
    @update:model-value="emit('update:modelValue', $event === true)"
  />
</template>
