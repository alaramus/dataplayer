<script setup lang="ts">
import { getCurrentInstance, onBeforeUnmount, onDeactivated, onMounted, useTemplateRef } from "vue"

// One delay for every tooltip in the application. Instant tooltips flicker as
// the pointer crosses a row of icon buttons.
const DELAY_MS = 250

/**
 * Structural, like the other template refs in this application: the one method
 * used is stated here rather than the whole Quasar component type imported.
 */
const tip = useTemplateRef<{ show: () => void; hide: () => void }>("tip")

withDefaults(
  defineProps<{
    /**
     * Beside its anchor rather than below it: a menu's line says why it is
     * off to the right of the menu, where it covers none of the other lines
     * — below, the reason for Paste lay over New schema (D187).
     */
    beside?: boolean
  }>(),
  { beside: false }
)

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

/**
 * A tooltip drawn only where the pointer is — one row of a grid rather than
 * every cell of it — is mounted after the pointer entered its anchor, and
 * Quasar shows one only on an entry it saw. So it is shown as if entered.
 */
const instance = getCurrentInstance()
let pending: ReturnType<typeof setTimeout> | undefined
onMounted(() => {
  const anchor = (instance?.proxy?.$el as Node | null | undefined)?.parentElement
  if (!anchor?.matches(":hover")) return
  pending = setTimeout(() => {
    if (anchor.matches(":hover")) tip.value?.show()
  }, DELAY_MS)
})
onBeforeUnmount(() => clearTimeout(pending))
</script>

<template>
  <q-tooltip
    ref="tip"
    :delay="DELAY_MS"
    class="app-tooltip"
    :anchor="beside ? 'center right' : undefined"
    :self="beside ? 'center left' : undefined"
    :offset="beside ? [20, 0] : undefined"
  >
    <slot />
  </q-tooltip>
</template>

<style>
/* Quasar's production stylesheet is linked after component CSS. Matching its
   tooltip class gives the kit's values enough specificity to survive that
   order, as they already do when Vite injects component CSS in development. */
.q-tooltip.app-tooltip {
  background: var(--dp-surface-raised);
  color: var(--dp-text);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
  padding: var(--dp-space-1) var(--dp-space-2);
  box-shadow: 0 2px 8px var(--dp-shadow-soft);
  max-width: var(--dp-width-note);
  white-space: normal;
  word-break: break-word;
}

/* Trap: a tooltip that does not fit below its anchor — every one over the bar
   at the foot of the screen — is flipped above it by Quasar, whose
   position-engine caps it at the height it measured. That measurement is an
   integer (`offsetHeight`), so at a browser zoom that is not a whole number
   the text is a fraction of a pixel taller than the cap: Quasar's own
   `overflow-y: auto` drew a scrollbar beside it, and hiding the overflow
   instead cut the descenders off ("http://", "The server's log"). A tooltip
   is never scrolled — the pointer cannot reach it (`no-pointer-events`) — so
   the pixel cap is traded for the viewport one the engine started from:
   small text always fits, and a tall tooltip still stays on screen. Two
   classes, to outweigh Quasar's one; `!important`, to outweigh the engine's
   inline pixel value. The same engine also narrows `max-width` to the rounded
   measured width when it nudges the tooltip to stay on screen (a rail icon
   at the very edge of the window): a fraction short of the true one-line
   width, it wrapped the text instead — "The server's" / "log",
   "http://localhost:800" / "0". The kit's own cap (--dp-width-note) is restored, so a
   short tooltip is one line again; long text still wraps by design. */
.q-tooltip.app-tooltip {
  overflow: hidden;
  max-width: var(--dp-width-note) !important;
  max-height: 65vh !important;
}
</style>
