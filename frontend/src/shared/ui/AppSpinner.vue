<script setup lang="ts">
// Waiting looks the same everywhere: centred, with room around it.
const SIZE = "28px"
</script>

<template>
  <div class="row justify-center q-pa-md">
    <q-spinner :size="SIZE" />
  </div>
</template>
