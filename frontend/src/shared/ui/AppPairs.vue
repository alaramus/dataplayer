<script setup lang="ts">
import { computed, provide } from "vue"

import { pairsArrowKey } from "./pairs"
import type { PairsArrow } from "./pairs"

/**
 * Which column becomes which: one pair to a row, under a legend that says which
 * side is which.
 *
 * Bringing rows in, creating a table from a file and creating one from rows ask
 * the same question, and three copies of this layout had already drifted — a
 * count beside the legend pushed its headings off the fields under them. One
 * pair to a row rather than two: two fitted more on the screen and left the
 * reader guessing which name belonged to which. Rows are AppPairsRow; the
 * legend's slots name the sides, `extra` a third column and `aside` a count at
 * the end of the legend.
 */
const props = withDefaults(defineProps<{ arrow?: PairsArrow }>(), { arrow: "forward" })

provide(pairsArrowKey, computed(() => props.arrow))
</script>

<template>
  <div
    class="app-pairs"
    :class="{ 'app-pairs--extra': Boolean($slots.extra) }"
  >
    <div class="app-pairs__legend dp-overline">
      <span><slot name="from" /></span>
      <span aria-hidden="true" />
      <span class="app-pairs__last">
        <span><slot name="to" /></span>
        <span
          v-if="$slots.aside && !$slots.extra"
          class="app-pairs__aside"
        ><slot name="aside" /></span>
      </span>
      <span
        v-if="$slots.extra"
        class="app-pairs__last"
      >
        <span><slot name="extra" /></span>
        <span
          v-if="$slots.aside"
          class="app-pairs__aside"
        ><slot name="aside" /></span>
      </span>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.app-pairs__legend,
.app-pairs :deep(.app-pairs-row) {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) 24px minmax(160px, 1.2fr);
  align-items: center;
  gap: var(--dp-space-2);
}
.app-pairs--extra .app-pairs__legend,
.app-pairs--extra :deep(.app-pairs-row) {
  grid-template-columns: minmax(140px, 1fr) 24px minmax(160px, 1.2fr) minmax(120px, 0.8fr);
}
.app-pairs__legend {
  padding-bottom: var(--dp-space-1);
  border-bottom: 1px solid var(--dp-border-faint);
}
.app-pairs__last {
  display: flex;
  align-items: baseline;
  gap: var(--dp-space-2);
  min-width: 0;
}
/* A count, not a heading: in the legend's case it would read as one. */
.app-pairs__aside {
  margin-inline-start: auto;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
}
.app-pairs :deep(.app-pairs-row) {
  padding: var(--dp-space-1) 0;
}
.app-pairs :deep(.app-pairs-row + .app-pairs-row) {
  border-top: 1px solid var(--dp-border-faint);
}
.app-pairs :deep(.app-pairs-row__cell) {
  min-width: 0;
  overflow-wrap: anywhere;
}
.app-pairs :deep(.app-pairs-row__arrow) {
  justify-self: center;
  color: var(--dp-text-faint);
}
/* A pair that fills nothing keeps its row — which columns there are is part of
   what the screen says — and loses the arrow, which would point nowhere. */
.app-pairs :deep(.app-pairs-row--idle .app-pairs-row__from) {
  color: var(--dp-text-muted);
}
.app-pairs :deep(.app-pairs-row--idle .app-pairs-row__arrow) {
  visibility: hidden;
}
/* A narrow form keeps the pairs side by side and drops the arrow, the one
   column that cannot shrink. */
@container app-form (max-width: 480px) {
  .app-pairs__legend,
  .app-pairs :deep(.app-pairs-row) {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  }
  .app-pairs--extra .app-pairs__legend,
  .app-pairs--extra :deep(.app-pairs-row) {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 0.8fr);
  }
  .app-pairs__legend > [aria-hidden="true"],
  .app-pairs :deep(.app-pairs-row__arrow) {
    display: none;
  }
}
</style>
