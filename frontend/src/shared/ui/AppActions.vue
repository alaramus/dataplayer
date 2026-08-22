<script setup lang="ts">
withDefaults(defineProps<{ align?: "left" | "right" }>(), { align: "right" })
</script>

<template>
  <q-card-actions :align="align">
    <slot />
  </q-card-actions>
</template>
