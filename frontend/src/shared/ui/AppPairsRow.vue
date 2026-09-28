<script setup lang="ts">
import { computed, inject } from "vue"

import { pairsArrowKey } from "./pairs"

/** One pair of AppPairs: `from`, the arrow, `to`, and `extra` where the legend has one. */
withDefaults(
  defineProps<{
    /** Nothing is filled by this pair; it stays on the list, quieter. */
    idle?: boolean
  }>(),
  { idle: false }
)

const arrow = inject(pairsArrowKey, computed(() => "forward" as const))
</script>

<template>
  <div
    class="app-pairs-row"
    :class="{ 'app-pairs-row--idle': idle }"
  >
    <div class="app-pairs-row__cell app-pairs-row__from">
      <slot name="from" />
    </div>
    <q-icon
      :name="arrow === 'back' ? 'arrow_back' : 'arrow_forward'"
      size="var(--dp-icon-sm)"
      class="app-pairs-row__arrow"
      aria-hidden="true"
    />
    <div class="app-pairs-row__cell">
      <slot name="to" />
    </div>
    <div
      v-if="$slots.extra"
      class="app-pairs-row__cell"
    >
      <slot name="extra" />
    </div>
  </div>
</template>
