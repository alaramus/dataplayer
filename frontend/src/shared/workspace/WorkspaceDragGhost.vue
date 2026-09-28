<script setup lang="ts">
import { panelColorStyle } from "@/shared/ui/panelColor"

import type { PanelLook } from "./context"

/**
 * The tab in the user's hand. It shows what a tab shows: a picture of the
 * panel would be a second render of it on every movement of the pointer, and
 * what is needed is which of several alike tabs was picked up.
 *
 * In the root rather than in the section the tab came from, because the
 * pointer leaves that section in the first moment of the gesture (G2).
 */
defineProps<{ look: PanelLook; x: number; y: number }>()
</script>

<template>
  <div
    class="drag-ghost"
    data-testid="workspace-drag-ghost"
    :style="{ ...panelColorStyle(look.color), left: `${String(x)}px`, top: `${String(y)}px` }"
  >
    <q-icon
      :name="look.icon"
      size="var(--dp-icon-sm)"
    />
    <span class="drag-ghost__title">{{ look.title }}</span>
    <span
      v-if="look.subtitle"
      class="drag-ghost__subtitle"
    >{{ look.subtitle }}</span>
  </div>
</template>

<style scoped>
.drag-ghost {
  position: fixed;
  /* Held at its middle, wherever the press landed on it. */
  transform: translate(-50%, -50%);
  /* Never a target: what is under the hand has to keep receiving the pointer,
     or no section would ever see the drag pass over it. */
  pointer-events: none;
  z-index: var(--dp-layer-drag);
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  max-width: 260px;
  padding: var(--dp-space-1) var(--dp-space-2);
  border: 1px solid var(--dp-border-strong);
  border-radius: var(--dp-radius-control);
  background: var(--dp-panel-background, var(--dp-surface-raised));
  color: var(--dp-panel-foreground, inherit);
  box-shadow: 0 4px 14px var(--dp-shadow);
  font-size: var(--dp-font-size-sm);
  white-space: nowrap;
  opacity: 0.9;
}
.drag-ghost__title {
  overflow: hidden;
  text-overflow: ellipsis;
}
.drag-ghost__subtitle {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 96px;
  color: var(--dp-panel-foreground, var(--dp-text-muted));
}
</style>
