<script setup lang="ts">
import AppTaskbarItem from "@/shared/ui/AppTaskbarItem.vue"

import type { WorkspaceContext } from "./context"

/**
 * The sections that are off the screen, on the bar at the foot of it.
 *
 * Beside the windows and drawn as they are, because it is the same fact about
 * both: something is open and not in front of you. A column pushed aside used
 * to be forty pixels of empty strip in the row it came from — room spent on a
 * handle — and the bar is where this application already keeps what is not on
 * the screen (D69, D92).
 *
 * Placed by the feature rather than by the engine: where the bar is belongs to
 * the application, and the engine has no notion of a footer.
 */
defineProps<{ context: WorkspaceContext }>()
</script>

<template>
  <nav
    v-if="context.aside.value.length"
    class="workspace-taskbar"
    aria-label="Sections put aside"
    data-testid="workspace-taskbar"
  >
    <AppTaskbarItem
      v-for="section in context.aside.value"
      :key="section.id"
      :title="`${section.title} · ${section.panels}`"
      :icon="section.icon"
      aside
      :tooltip="`Bring back ${section.title}`"
      :data-testid="`workspace-aside-${section.id}`"
      @open="context.bringBack(section.id)"
    />
  </nav>
</template>

<style scoped>
/* The same row the windows are in, so the two read as one bar. */
.workspace-taskbar {
  display: flex;
  align-items: center;
  align-self: center;
  gap: var(--dp-space-1);
  min-width: 0;
  max-height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  font-size: 12px;
}
</style>
