<script setup lang="ts">
/**
 * One setting of a page of them: the question on the left and its answer on
 * the right, so a page of settings reads down one column of controls rather
 * than as a stack of forms. The control goes in the default slot.
 */
defineProps<{
  title: string
  /** What the setting does and where it is kept. */
  summary?: string
}>()
</script>

<template>
  <section class="app-setting-row">
    <div class="app-setting-row__what">
      <span class="app-setting-row__title">{{ title }}</span>
      <span
        v-if="summary"
        class="dp-helper"
      >{{ summary }}</span>
    </div>
    <div class="app-setting-row__control">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.app-setting-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--dp-side-column-width);
  gap: var(--dp-space-5);
  align-items: start;
  padding: var(--dp-space-4) 0;
  border-bottom: 1px solid var(--dp-border);
}
.app-setting-row__what {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.app-setting-row__title {
  font-weight: 500;
}
.app-setting-row__control {
  min-width: 0;
}
/* Narrow: the control goes under the question it answers. */
@media (max-width: 700px) {
  .app-setting-row {
    grid-template-columns: 1fr;
  }
}
</style>
