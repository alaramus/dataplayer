<script setup lang="ts">
import type { PageSection } from "./sections"

/**
 * A page made of sections: the list of them beside what the current one
 * shows. The list is the page's own navigation — the address names the
 * section — so choosing one is the caller's to route.
 */
defineProps<{
  sections: readonly PageSection[]
  current: string
  /** Names the layout, its list and each entry: `preferences-section-general`. */
  testid: string
}>()

const emit = defineEmits<{ select: [id: string] }>()
</script>

<template>
  <div
    class="app-sections"
    :data-testid="testid"
  >
    <nav
      class="app-sections__list"
      :data-testid="`${testid}-sections`"
    >
      <button
        v-for="section in sections"
        :key="section.id"
        type="button"
        class="app-sections__entry"
        :class="{ 'app-sections__entry--current': section.id === current }"
        :aria-current="section.id === current ? 'page' : undefined"
        :data-testid="`${testid}-section-${section.id}`"
        @click="emit('select', section.id)"
      >
        <q-icon
          :name="section.icon"
          size="var(--dp-icon-sm)"
        />
        <span class="app-sections__text">
          <span class="app-sections__title">{{ section.title }}</span>
          <span class="dp-helper">{{ section.summary }}</span>
        </span>
      </button>
    </nav>

    <section class="app-sections__body">
      <slot />
    </section>
  </div>
</template>

<style scoped>
.app-sections {
  display: grid;
  grid-template-columns: var(--dp-side-column-width) 1fr;
  gap: var(--dp-space-5);
  align-items: start;
  min-height: 0;
}
.app-sections__list {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.app-sections__entry {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
  border: 0;
  border-radius: var(--dp-radius-control);
  background: transparent;
  color: var(--dp-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.app-sections__entry:hover {
  background: var(--dp-hover);
}
/* The section shown is the current page of a list, marked as a tab is (D186). */
.app-sections__entry--current {
  background: var(--dp-tab-current);
}
.app-sections__text {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-half);
  min-width: 0;
}
.app-sections__title {
  font-weight: 500;
}
.app-sections__body {
  min-width: 0;
}
/* A narrow window puts the list above what it opens rather than beside it. */
@media (max-width: 900px) {
  .app-sections {
    grid-template-columns: 1fr;
  }
}
</style>
