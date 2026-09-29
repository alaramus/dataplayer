<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<template>
  <div class="app-page-header">
    <h1 class="dp-page-title">
      {{ title }}
    </h1>
    <div class="app-page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.app-page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
  margin-bottom: var(--dp-space-4);
}
.app-page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
/* A flat button's text is what the eye takes for its edge; pulled out by its
   own padding, it ends where the content under the head ends, as a filled
   button there does. */
.app-page-header__actions > :deep(.q-btn--flat:last-child) {
  margin-inline-end: calc(-1 * var(--dp-space-4));
}
</style>
