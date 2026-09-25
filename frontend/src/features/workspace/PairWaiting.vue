<script setup lang="ts">
import { computed } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { AppButton, AppIconButton, AppMenu, appIcons } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

import type { PairsApi } from "./usePairs"

/**
 * The pair waiting for its second catalog, in the header (D167).
 *
 * Only remembered: nothing opens until the second arrives, dropped on the
 * empty place or chosen from the list behind it — the whole gesture without a
 * pointer. The cross forgets it.
 */
const props = defineProps<{ pairs: PairsApi }>()
const connectors = useConnectors()

const others = computed<MenuItem[]>(() => {
  const waiting = props.pairs.waiting.value
  return (connectors.data.value?.data ?? [])
    .filter((connector) => connector.enabled && connector.id !== waiting?.connectorId)
    .map((connector) => ({ name: connector.id, label: connector.name }))
})

function choose(connectorId: string) {
  const connector = connectors.data.value?.data.find((one) => one.id === connectorId)
  if (connector !== undefined) props.pairs.pairWith(connector)
}
</script>

<template>
  <span
    v-if="pairs.waiting.value"
    class="pair-waiting"
    data-testid="pair-waiting"
  >
    <q-icon
      :name="appIcons.pair"
      size="18px"
    />
    <span class="pair-waiting__first">{{ pairs.waiting.value.title }}</span>
    <AppButton
      variant="secondary"
      size="sm"
      label="Choose the second connection"
      data-testid="pair-waiting-choose"
    >
      <AppMenu
        :items="others"
        @select="choose"
      />
    </AppButton>
    <AppIconButton
      :icon="appIcons.close"
      tooltip="Forget this pair"
      data-testid="pair-waiting-cancel"
      @click="pairs.cancel()"
    />
  </span>
</template>

<style scoped>
.pair-waiting {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-2);
  margin-left: var(--dp-space-3);
  padding: 0 var(--dp-space-1) 0 var(--dp-space-2);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  background: var(--dp-surface);
  font-size: var(--dp-font-size);
}
.pair-waiting__first {
  color: var(--dp-text-strong);
}
</style>
