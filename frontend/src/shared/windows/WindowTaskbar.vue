<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"

import AppButton from "@/shared/ui/AppButton.vue"
import AppIconButton from "@/shared/ui/AppIconButton.vue"
import AppTooltip from "@/shared/ui/AppTooltip.vue"
import { panelColorStyle } from "@/shared/ui/panelColor"

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
    <div
      v-for="entry in items"
      :key="entry.key"
      class="window-taskbar__item"
      :class="{
        'window-taskbar__item--front': isFront(entry),
        'window-taskbar__item--aside': entry.minimized,
      }"
      :style="panelColorStyle(entry.look.color)"
    >
      <AppButton
        class="window-taskbar__open"
        variant="quiet"
        size="sm"
        :icon="entry.look.icon ?? 'web_asset'"
        :aria-label="entry.look.title"
        :aria-pressed="isFront(entry)"
        :data-testid="`window-tab-${entry.id}`"
        :data-window-key="entry.key"
        @click="toggle(entry)"
      >
        <span class="window-taskbar__title">{{ entry.look.title }}</span>
        <AppTooltip>{{ entry.look.title }}</AppTooltip>
      </AppButton>
      <AppIconButton
        class="window-taskbar__close"
        icon="close"
        compact
        :tooltip="`Close ${entry.look.title}`"
        :aria-label="`Close ${entry.look.title}`"
        :data-testid="`window-tab-close-${entry.id}`"
        @click="context.requestClose(entry.id)"
      />
    </div>
  </nav>
</template>

<style scoped>
.window-taskbar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  min-width: 0;
  overflow-x: auto;
  font-size: 12px;
}
.window-taskbar__item {
  flex: none;
  display: flex;
  align-items: center;
  max-width: 240px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: var(--dp-panel-background, var(--dp-hover));
  color: var(--dp-panel-foreground, inherit);
}
/* The window one is actually looking at, marked the way a desktop marks it. */
.window-taskbar__item--front {
  border-color: var(--dp-focus-border);
  background: var(--dp-panel-background, var(--dp-active));
}
/* Put aside: still on the bar, and visibly not on screen. */
.window-taskbar__item--aside {
  opacity: 0.65;
}
.window-taskbar__open :deep(.q-btn__content) {
  flex-wrap: nowrap;
  gap: var(--dp-space-1);
}
.window-taskbar__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
