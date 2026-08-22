<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="row items-center justify-between q-mb-md">
    <div class="text-h5">
      {{ title }}
    </div>
    <div class="row items-center q-gutter-sm">
      <slot name="actions" />
    </div>
  </div>
</template>
