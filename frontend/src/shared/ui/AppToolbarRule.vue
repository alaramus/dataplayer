<script setup lang="ts">
/**
 * The line between two groups of commands in a row of them.
 *
 * It stretches to the height of what holds it, less a step at each end, so
 * the row decides how tall it is. The group on its right draws it: a group
 * that is not shown then takes its line away with it.
 */
</script>

<template>
  <span
    class="app-toolbar-rule"
    aria-hidden="true"
  />
</template>

<style scoped>
.app-toolbar-rule {
  flex: none;
  align-self: stretch;
  width: 1px;
  margin: var(--dp-space-1) var(--dp-space-2);
  background: var(--dp-border);
}
</style>
