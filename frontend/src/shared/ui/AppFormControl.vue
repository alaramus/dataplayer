<script setup lang="ts">
import { inject } from "vue"

import { formLayoutKey } from "./formLayout"

/**
 * What belongs to the field above it without being a field: where a walk has
 * got to, the list to pick the next step from, a line about the value.
 *
 * In a form it stands in the control column, under what it answers to, and
 * goes back to the edge when the form is narrow enough for labels to move
 * above their fields. Outside a form it is a plain block.
 */
const formLayout = inject(formLayoutKey, false)
</script>

<template>
  <div
    class="app-form-control"
    :class="{ 'app-form-control--form': formLayout }"
  >
    <slot />
  </div>
</template>

<style scoped>
.app-form-control {
  min-width: 0;
}
.app-form-control--form {
  margin-left: var(--dp-form-label-width);
}
.app-form--labels-above .app-form-control--form {
  margin-left: 0;
}
@container app-form (max-width: 480px) {
  .app-form-control--form {
    margin-left: 0;
  }
}
</style>
