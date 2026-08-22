<script setup lang="ts">
// One delay for every tooltip in the application. Instant tooltips flicker as
// the pointer crosses a row of icon buttons.
const DELAY_MS = 250
</script>

<template>
  <q-tooltip :delay="DELAY_MS">
    <slot />
  </q-tooltip>
</template>
