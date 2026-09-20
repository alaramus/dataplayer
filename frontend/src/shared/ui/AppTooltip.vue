<script setup lang="ts">
import { onDeactivated, useTemplateRef } from "vue"

// One delay for every tooltip in the application. Instant tooltips flicker as
// the pointer crosses a row of icon buttons.
const DELAY_MS = 250

/**
 * Structural, like the other template refs in this application: the one method
 * used is stated here rather than the whole Quasar component type imported.
 */
const tip = useTemplateRef<{ hide: () => void }>("tip")

/**
 * A tab that is switched away from takes its tooltips with it.
 *
 * A tooltip hides when the pointer leaves the button under it, and pressing a
 * button that opens another tab is the one case where that never happens: the
 * pointer does not leave, the button does. The tab is kept rather than
 * destroyed, so no `mouseleave` is raised, and the tooltip — teleported to the
 * body — stayed drawn over whichever tab came next. Being put away is a reason
 * to hide, exactly as leaving is.
 */
onDeactivated(() => {
  tip.value?.hide()
})
</script>

<template>
  <q-tooltip
    ref="tip"
    :delay="DELAY_MS"
    class="app-tooltip"
  >
    <slot />
  </q-tooltip>
</template>

<style>
.app-tooltip {
  background: var(--dp-surface-raised);
  color: var(--dp-text-strong);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  font-size: 12px;
  line-height: 1.4;
  padding: var(--dp-space-1) var(--dp-space-2);
  box-shadow: 0 2px 8px var(--dp-shadow-soft);
  max-width: 240px;
  white-space: normal;
  word-break: break-word;
}

/* Trap: a tooltip that does not fit below its anchor — every one over the bar
   at the foot of the screen — is flipped above it by Quasar and capped at the
   height it measured, which is rounded. At a browser zoom that is not a whole
   number the text is a fraction of a pixel taller than that, and Quasar's own
   `overflow-y: auto` drew a scrollbar beside it. A tooltip is never scrolled:
   the pointer cannot reach it. Two classes, to outweigh Quasar's one. */
.q-tooltip.app-tooltip {
  overflow: hidden;
}
</style>
