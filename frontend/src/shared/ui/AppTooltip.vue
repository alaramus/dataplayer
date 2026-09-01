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
 * A tooltip hides when the pointer leaves the button under it. Pressing a
 * button that opens another tab is the one case where that never happens: the
 * pointer does not leave, the button does. A tab that is not showing is kept
 * rather than destroyed, so nothing is unmounted and no `mouseleave` is
 * raised, and the tooltip is teleported to the body — it stayed drawn over
 * whichever tab came next until the same button was hovered and left again.
 * Being put away is a reason to hide, exactly as leaving is.
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
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.4;
  padding: 4px 8px;
  box-shadow: 0 2px 8px var(--dp-shadow-soft);
  max-width: 240px;
  white-space: normal;
  word-break: break-word;
}
</style>
