<script setup lang="ts">
import { inject } from "vue"

import { formLayoutKey } from "./formLayout"
import { checkboxLook } from "./tokens"

const formLayout = inject(formLayoutKey, false)
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
    :class="{ 'app-form-checkbox': formLayout }"
    v-bind="checkboxLook(formLayout, dense)"
    :model-value="indeterminate ? null : modelValue"
    :toggle-indeterminate="false"
    :label="label"
    @update:model-value="emit('update:modelValue', $event === true)"
  />
</template>

<style scoped>
/* Trap: Quasar grows the halo behind a tick box with scale3d(), and a 3D
   transform gives every box a compositor layer of its own, hovered or not. A
   catalog level of two hundred rows was two hundred layers, and every frame of
   the workspace spent a hundred milliseconds and more arranging them. The same
   halo scaled in 2D is painted with the page. Quasar's three selectors, each
   outweighed by the scope's attribute. */
body.desktop .q-checkbox:not(.disabled) :deep(.q-checkbox__inner)::before {
  transform: scale(0);
}
body.desktop .q-checkbox:not(.disabled):is(:focus, :hover) :deep(.q-checkbox__inner)::before {
  transform: scale(1);
}
body.desktop .q-checkbox--dense:not(.disabled):is(:focus, :hover) :deep(.q-checkbox__inner)::before {
  transform: scale(1.4);
}
</style>
