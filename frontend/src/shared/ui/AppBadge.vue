<script setup lang="ts">
import { computed } from "vue"

import { toneFill } from "./tokens"
import type { Tone } from "./tokens"

const props = withDefaults(
  defineProps<{
    label: string
    tone?: Tone
    /**
     * Hung off the top right corner of the button it is placed in, as a count
     * on a rail button is: in the flow it would widen a button that stands in
     * a row of equal ones and push its icon off the axis.
     */
    corner?: boolean
  }>(),
  { tone: "info", corner: false }
)

const fill = computed(() => toneFill(props.tone))
</script>

<template>
  <q-badge
    :label="label"
    :class="[fill, { 'app-badge--corner': corner }]"
  />
</template>

<style scoped>
/* A Quasar button is positioned already, so this lands on its corner. */
.app-badge--corner {
  position: absolute;
  top: 1px;
  right: 0;
  min-width: 16px;
  padding: 1px var(--dp-space-1);
  font-size: var(--dp-font-size-xs);
  line-height: 12px;
  justify-content: center;
}
</style>
