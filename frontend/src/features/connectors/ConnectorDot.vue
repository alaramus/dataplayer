<script setup lang="ts">
import { computed } from "vue"

import { badgeColor } from "@/shared/ui"
import { useConnectorChecksStore } from "@/stores/connectorChecks"
import type { CheckState } from "@/stores/connectorChecks"

/**
 * What the last check of a connection said, as one dot.
 *
 * A component of its own because two places show it — the list and the strip
 * a collapsed column leaves behind — and a second copy of the table below is a
 * second thing to keep in step. Nothing checked has no tone of its own: it is
 * an absence, not a warning.
 */
const props = defineProps<{ connectorId: string; name: string }>()

const checks = useConnectorChecksStore()

const TONE: Record<CheckState, string> = {
  unknown: "connector-dot--unknown",
  ok: `bg-${badgeColor("success")}`,
  failed: `bg-${badgeColor("error")}`,
}

const state = computed(() => checks.stateOf(props.connectorId))
</script>

<template>
  <span
    class="connector-dot"
    :class="TONE[state]"
    :data-testid="`connector-state-${name}`"
    :data-state="state"
  />
</template>

<style scoped>
.connector-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.connector-dot--unknown {
  background: var(--dp-idle);
}
</style>
