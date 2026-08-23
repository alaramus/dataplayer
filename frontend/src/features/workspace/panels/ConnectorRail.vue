<script setup lang="ts">
import { computed } from "vue"

import ConnectorDot from "@/features/connectors/ConnectorDot.vue"
import { useConnectors } from "@/features/connectors/api"
import { adapterIcon } from "@/features/connectors/adapters"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppIconButton } from "@/shared/ui"

/**
 * The connections while their column is pushed aside.
 *
 * What survives the width is what a row is for: which source it is, and what
 * the last check said. The name goes, because at forty pixels it would be one
 * letter. A click opens the catalog — the same thing the row does — rather
 * than the window of the connection: a collapsed column is a way back into a
 * source, and the window can still be opened from the head of the catalog.
 */
const workspace = useWorkspaceActions()
const connectors = useConnectors()

const rows = computed(() => connectors.data.value?.data ?? [])
</script>

<template>
  <div
    class="connector-rail"
    data-testid="connector-rail"
  >
    <div
      v-for="connector in rows"
      :key="connector.id"
      class="connector-rail__slot"
      :class="{
        'connector-rail__slot--selected': connector.id === workspace.activeConnectorId.value,
      }"
    >
      <AppIconButton
        :icon="adapterIcon(connector.adapter_type)"
        :tooltip="connector.name"
        :data-testid="`connector-rail-${connector.name}`"
        @click="workspace.openCatalog(connector)"
      />
      <ConnectorDot
        class="connector-rail__dot"
        :connector-id="connector.id"
        :name="connector.name"
      />
    </div>
  </div>
</template>

<style scoped>
.connector-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2px 0;
}
.connector-rail__slot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}
.connector-rail__slot--selected {
  background: rgba(25, 118, 210, 0.12);
}
/* On the icon rather than beside it: there is no room for a second column. */
.connector-rail__dot {
  position: absolute;
  right: 1px;
  bottom: 1px;
  border: 1px solid #fff;
  pointer-events: none;
}
</style>
