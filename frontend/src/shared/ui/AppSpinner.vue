<script setup lang="ts">
// Waiting looks the same everywhere: centred, with room around it — or, inline,
// the size of an icon beside the words that say what is awaited.
defineProps<{ inline?: boolean }>()
const SIZE = "28px"
</script>

<template>
  <q-spinner
    v-if="inline"
    size="var(--dp-icon-sm)"
  />
  <div
    v-else
    class="row justify-center q-pa-md"
  >
    <q-spinner :size="SIZE" />
  </div>
</template>
