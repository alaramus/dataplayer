<script setup lang="ts">
import { computed } from "vue"

import { describeState } from "@/features/connectors/connectorState"
import type { ConnectorState } from "@/features/connectors/connectorState"
import { badgeColor } from "@/shared/ui"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

/**
 * What state a connection is in, as one dot. Its own component because the
 * list and the collapsed strip both show it.
 *
 * The words that go with the tone are the icon's business: this dot is drawn
 * over the icon with pointer events off, so a tooltip of its own would never
 * be hovered. Nothing checked has no tone — that is an absence, not a warning.
 */
const props = withDefaults(
  defineProps<{ connectorId: string; name: string; enabled?: boolean }>(),
  { enabled: true }
)

const checks = useConnectorChecksStore()

const TONE: Record<ConnectorState, string> = {
  // Switched off is a warning and not a failure: nothing is wrong with it,
  // it is simply not in use.
  disabled: `bg-${badgeColor("warning")}`,
  unknown: "connector-dot--unknown",
  ok: `bg-${badgeColor("success")}`,
  failed: `bg-${badgeColor("error")}`,
}

const state = computed(
  () => describeState(props.enabled, checks.reportOf(props.connectorId)).state
)
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
