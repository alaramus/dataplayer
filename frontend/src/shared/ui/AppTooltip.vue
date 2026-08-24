<script setup lang="ts">
// One delay for every tooltip in the application. Instant tooltips flicker as
// the pointer crosses a row of icon buttons.
const DELAY_MS = 250
</script>

<template>
  <q-tooltip
    :delay="DELAY_MS"
    class="app-tooltip"
  >
    <slot />
  </q-tooltip>
</template>

<style>
.app-tooltip {
  background: var(--dp-surface-raised);
  color: var(--dp-text-strong);
  border: 1px solid var(--dp-border);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.4;
  padding: 4px 8px;
  box-shadow: 0 2px 8px var(--dp-shadow-soft);
  max-width: 240px;
  white-space: normal;
  word-break: break-word;
}
</style>
