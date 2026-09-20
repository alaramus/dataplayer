<script setup lang="ts">
import { provide } from "vue"

import { formLayoutKey } from "./formLayout"

provide(formLayoutKey, true)
</script>

<template>
  <div class="app-form">
    <slot />
  </div>
</template>

<style scoped>
.app-form {
  container: app-form / inline-size;
  min-width: 0;
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
.app-form :deep(.app-form-field .q-field__bottom) {
  padding: var(--dp-space-1) 0 0;
}
@container app-form (max-width: 480px) {
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
