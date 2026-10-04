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
    disable?: boolean
  }>(),
  { label: undefined, indeterminate: false, dense: false, disable: false }
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
    :disable="disable"
    @update:model-value="emit('update:modelValue', $event === true)"
  />
</template>

<style scoped>
/* Drawn the way the kit draws its other marks: the size of an icon in a line
   of text, a hairline edge and the control corner. Quasar's box was 18px with
   a 2px edge, twice the weight of the 16px icons beside it. Each selector
   outweighs Quasar's own by the scope's attribute. */
.q-checkbox :deep(.q-checkbox__inner) {
  width: var(--dp-icon-sm);
  min-width: var(--dp-icon-sm);
  height: var(--dp-icon-sm);
  color: var(--dp-text-muted);
}
.q-checkbox:not(.disabled):hover :deep(.q-checkbox__inner) {
  color: var(--dp-text);
}
.q-checkbox :deep(.q-checkbox__bg) {
  inset: 1px;
  width: auto;
  height: auto;
  border-width: 1px;
  border-radius: var(--dp-radius-control);
}
.q-checkbox :deep(.q-checkbox__svg) {
  color: var(--dp-on-action-primary);
}
/* Trap: Quasar grows a round halo behind the box with scale3d(), and a 3D
   transform gives every box a compositor layer of its own, hovered or not; a
   catalog level of two hundred rows spent a hundred milliseconds a frame
   arranging them. The edge darkening under the pointer replaces the halo, so
   it is not drawn at all — by a selector as long as Quasar's, which a shorter
   one silently lost to. */
body.desktop .q-checkbox:not(.disabled) :deep(.q-checkbox__inner)::before {
  content: none;
}
/* The halo was also the only mark of focus; this is the ring every button
   carries (theme.css). */
.q-checkbox:focus-visible :deep(.q-checkbox__bg) {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: var(--dp-space-half);
}
.q-checkbox :deep(.q-checkbox__label) {
  padding-left: var(--dp-space-2);
}
/* Undense, Quasar's box stood in a 40px square for its halo; now it stands
   as tall as the buttons beside it. */
.q-checkbox:not(.q-checkbox--dense) {
  min-height: var(--dp-control-height);
}
</style>
