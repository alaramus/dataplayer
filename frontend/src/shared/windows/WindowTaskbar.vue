<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"

import AppTaskbarItem from "@/shared/ui/AppTaskbarItem.vue"

import type { WindowState, WindowsContext } from "./useWindows"

/**
 * Every open window as a button in the footer, the way a desktop draws its
 * taskbar: a window is on the bar from the moment it opens rather than only
 * once it has been put aside, and it can be closed from here without being
 * brought back first.
 *
 * Ordered by when they opened rather than by the stacking order the manager
 * keeps, because buttons that rearrange themselves as one window is focused
 * after another cannot be aimed at.
 */
const props = defineProps<{ context: WindowsContext }>()
const bar = ref<HTMLElement | null>(null)

const items = computed(() =>
  [...props.context.windows.value].sort((one, other) => one.key - other.key)
)

function isFront(entry: WindowState) {
  return !entry.minimized && props.context.frontId.value === entry.id
}

/** The taskbar gesture: the window being looked at goes away, any other comes. */
function toggle(entry: WindowState) {
  if (isFront(entry)) props.context.minimize(entry.id)
  else props.context.focus(entry.id)
}

// Focus follows a window that has just been put aside: its button is the only
// thing left on screen that leads back to it.
watch(
  () =>
    props.context.windows.value
      .filter((entry) => entry.minimized)
      .map((entry) => entry.key),
  async (keys, previous) => {
    const added = keys.find((key) => !previous.includes(key))
    if (added === undefined) return
    await nextTick()
    bar.value?.querySelector<HTMLElement>(`[data-window-key="${added}"]`)?.focus()
  }
)
</script>

<template>
  <nav
    v-if="items.length"
    ref="bar"
    class="window-taskbar"
    aria-label="Open windows"
    data-testid="window-taskbar"
  >
    <AppTaskbarItem
      v-for="entry in items"
      :key="entry.key"
      :title="entry.look.title"
      :icon="entry.look.icon ?? 'web_asset'"
      :color="entry.look.color"
      :front="isFront(entry)"
      :aside="entry.minimized"
      :close-label="`Close ${entry.look.title}`"
      :close-test-id="`window-tab-close-${entry.id}`"
      :data-testid="`window-tab-${entry.id}`"
      :data-window-key="entry.key"
      @open="toggle(entry)"
      @close="context.requestClose(entry.id)"
    />
  </nav>
</template>

<style scoped>
.window-taskbar {
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
