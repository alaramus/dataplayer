<script setup lang="ts">
import { provide } from "vue"

import { formLayoutKey } from "./formLayout"

withDefaults(defineProps<{
  /** A standalone form owns its padding and field spacing; an embedded one does not. */
  layout?: "embedded" | "section" | "grid"
}>(), { layout: "embedded" })

provide(formLayoutKey, true)
</script>

<template>
  <div
    class="app-form"
    :class="{
      'app-form--section': layout === 'section',
      'app-form--grid': layout === 'grid',
    }"
  >
    <slot />
  </div>
</template>

<style scoped>
.app-form {
  container: app-form / inline-size;
  min-width: 0;
}
.app-form--section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
  padding: var(--dp-space-4);
  overflow-wrap: anywhere;
}
.app-form :deep(.app-form-field .q-field__before) {
  width: var(--dp-form-label-width);
  flex: none;
  padding-right: var(--dp-space-3);
  font-size: var(--dp-font-size);
  color: inherit;
}
.app-form :deep(.app-form-field .q-field__control),
.app-form :deep(.app-form-field .q-field__marginal) {
  min-height: var(--dp-form-control-height);
  height: auto;
}
.app-form :deep(.app-form-field .q-field__control) {
  border-radius: var(--dp-radius-control);
  background: var(--dp-field-surface);
}
.app-form :deep(.app-form-field .q-field__control::before) {
  border-color: var(--dp-field-border);
}
.app-form :deep(.app-form-field .q-field__control-container) {
  padding-top: 0;
}
/* Quasar's dense, labelled QSelect has an equally specific top inset in its
   production stylesheet, which is loaded after this component's CSS. Keep its
   control aligned with AppInput in both development and built bundles. */
.app-form :deep(.app-form-field.q-field--auto-height.q-field--labeled .q-field__control-container) {
  padding-top: 0;
}
/* QSelect derives the combobox name from its label prop, not $attrs. */
.app-form :deep(.app-form-field .q-field__label) {
  display: none;
}
.app-form :deep(.app-form-field .q-field__native),
.app-form :deep(.app-form-field .q-field__input) {
  min-height: var(--dp-form-control-height);
  padding-top: 0;
  padding-bottom: 0;
}
.app-form :deep(.app-form-field.q-field--auto-height.q-field--labeled .q-field__native) {
  min-height: var(--dp-form-control-height);
  padding-top: 0;
  padding-bottom: 0;
}
/* Trap: Quasar insets an autofilled input by a pixel above and below, which
   its own fixed-height control absorbs. This control grows with what is in
   it, so a field stood two pixels taller while the browser offered or put in
   a value, and the form below it moved under the pointer. */
.app-form :deep(.app-form-field .q-field__native:-webkit-autofill),
.app-form :deep(.app-form-field .q-field__input:-webkit-autofill) {
  min-height: calc(var(--dp-form-control-height) - 2px);
}
.app-form :deep(.app-form-field .q-field__bottom) {
  padding: var(--dp-space-1) 0 0;
}
.app-form :deep(.app-form-field .q-field__after) {
  height: var(--dp-form-control-height);
}
.app-form :deep(.app-form-checkbox) {
  margin-left: var(--dp-form-label-width);
  min-height: var(--dp-form-control-height);
}
.app-form--grid :deep(.app-form-checkbox) {
  margin-left: 0;
}
.app-form--grid :deep(.app-form-field) {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
}
.app-form--grid :deep(.app-form-field > .q-field__inner) {
  width: 100%;
}
.app-form--grid :deep(.app-form-field .q-field__before) {
  grid-column: 1 / -1;
  width: auto;
  min-height: 0;
  padding: 0 0 var(--dp-space-1);
}
.app-form--grid :deep(.app-form-field .q-field__after) {
  grid-column: 2;
  grid-row: 2;
}
@container app-form (max-width: 480px) {
  .app-form :deep(.app-form-checkbox) {
    margin-left: 0;
  }
  .app-form :deep(.app-form-field > .q-field__inner > .q-field__control),
  .app-form :deep(.app-form-field > .q-field__control) {
    min-width: 0;
  }
  .app-form :deep(.app-form-field) {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .app-form :deep(.app-form-field > .q-field__inner) {
    width: 100%;
  }
  .app-form :deep(.app-form-field .q-field__before) {
    grid-column: 1 / -1;
    width: auto;
    min-height: 0;
    padding: 0 0 var(--dp-space-1);
  }
  .app-form :deep(.app-form-field .q-field__after) {
    grid-column: 2;
    grid-row: 2;
  }
}
</style>
