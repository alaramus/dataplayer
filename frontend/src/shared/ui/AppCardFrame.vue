<script setup lang="ts">
/**
 * A card of the working screens: its own ground, its own edge, its own
 * corners, and a column that clips what it holds. Its head is AppCardHead.
 *
 * A Data section draws the same frame in WorkspaceLeaf rather than through
 * this: its root carries the drag handlers and is measured as an element.
 */
withDefaults(defineProps<{ tag?: "div" | "section" | "aside" | "main" }>(), { tag: "div" })
</script>

<template>
  <component
    :is="tag"
    class="app-card-frame"
  >
    <slot />
  </component>
</template>

<style scoped>
.app-card-frame {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  box-sizing: border-box;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface);
}
</style>
