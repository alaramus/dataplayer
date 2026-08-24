<script setup lang="ts">
import { computed } from "vue"

import ConnectorDot from "@/features/connectors/ConnectorDot.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import { describeState } from "@/features/connectors/connectorState"
import { AppIconButton } from "@/shared/ui"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

/**
 * A connection, as one thing to press: the logo of its source type with the
 * state dot standing on it.
 *
 * One component because both columns show it — the list and the strip a
 * collapsed column leaves behind — and they have to be the same thing: pushing
 * the column aside is meant to take away the name and nothing else, which two
 * copies of this markup would not survive. What a press means is still the
 * caller's: in the list it opens the connection, in the strip it opens the
 * catalog.
 *
 * The state is said in words here rather than on the dot, which has pointer
 * events off and could never be hovered.
 */
const props = withDefaults(
  defineProps<{
    connectorId: string
    name: string
    adapterType: string
    tooltip: string
    testid: string
    enabled?: boolean
  }>(),
  { enabled: true }
)

const emit = defineEmits<{ click: [] }>()

const checks = useConnectorChecksStore()

const explained = computed(
  () => `${props.tooltip} · ${describeState(props.enabled, checks.reportOf(props.connectorId)).words}`
)
</script>

<template>
  <span
    class="connector-icon"
    :class="{ 'connector-icon--off': !enabled }"
  >
    <AppIconButton
      :icon="adapterIcon(adapterType)"
      :tooltip="explained"
      :data-testid="testid"
      @click="emit('click')"
    />
    <ConnectorDot
      class="connector-icon__dot"
      :connector-id="connectorId"
      :name="name"
      :enabled="enabled"
    />
  </span>
</template>

<style scoped>
.connector-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
/* On the icon rather than beside it: at the width of a pushed-aside column
   there is no room for a second column, and the wide list shows the same thing
   in the same place so that collapsing moves nothing. */
.connector-icon__dot {
  position: absolute;
  right: 1px;
  bottom: 1px;
  border: 1px solid var(--dp-surface);
  pointer-events: none;
}
/* A switched-off connection is still listed and still editable, so it is
   dimmed rather than hidden. */
.connector-icon--off {
  opacity: 0.55;
}
</style>
