<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"

import AppButton from "@/shared/ui/AppButton.vue"
import AppTooltip from "@/shared/ui/AppTooltip.vue"
import { panelColorStyle } from "@/shared/ui/panelColor"

import type { WindowsContext } from "./useWindows"

const props = defineProps<{ context: WindowsContext }>()
const bar = ref<HTMLElement | null>(null)
const minimized = computed(() =>
  props.context.windows.value.filter((entry) => entry.minimized)
)

watch(
  () => minimized.value.map((entry) => entry.key),
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
    v-if="minimized.length"
    ref="bar"
    class="window-taskbar"
    aria-label="Minimized windows"
    data-testid="window-taskbar"
  >
    <span class="window-taskbar__label">Minimized ({{ minimized.length }})</span>
    <div class="window-taskbar__items">
      <AppButton
        v-for="entry in minimized"
        :key="entry.key"
        class="window-taskbar__item"
        :style="panelColorStyle(entry.look.color)"
        variant="quiet"
        size="sm"
        :icon="entry.look.icon ?? 'web_asset'"
        :aria-label="`Restore ${entry.look.title}`"
        :data-testid="`window-restore-${entry.id}`"
        :data-window-key="entry.key"
        @click="context.focus(entry.id)"
      >
        <span class="window-taskbar__title">{{ entry.look.title }}</span>
        <AppTooltip>Restore {{ entry.look.title }}</AppTooltip>
      </AppButton>
    </div>
  </nav>
</template>

<style scoped>
.window-taskbar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-width: 0;
  padding: 0 var(--dp-space-3);
  border-top: 1px solid var(--dp-border);
  font-size: 12px;
}
.window-taskbar__label {
  flex: none;
  color: var(--dp-text-muted);
}
.window-taskbar__items {
  display: flex;
  gap: var(--dp-space-1);
  min-width: 0;
  overflow-x: auto;
}
.window-taskbar__item {
  flex: none;
  max-width: 240px;
  background: var(--dp-panel-background, transparent);
  color: var(--dp-panel-foreground, inherit);
}
.window-taskbar__item :deep(.q-btn__content) {
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
