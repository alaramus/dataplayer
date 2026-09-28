<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="row items-center justify-between q-mb-md">
    <h1 class="dp-page-title">
      {{ title }}
    </h1>
    <div class="row items-center q-gutter-sm">
      <slot name="actions" />
    </div>
  </div>
</template>
