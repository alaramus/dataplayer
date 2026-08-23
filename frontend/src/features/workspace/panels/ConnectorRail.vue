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
 *
 * Adding one survives the width too. A column pushed aside is the same
 * commands at a smaller size, not a smaller set of them — and the button
 * makes the same call the wide panel makes rather than its own copy of what
 * "new connection" means.
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
    <!-- The same test id the wide panel carries, because it is the same
         action: the strip and the panel stand under v-if/v-else in the
         section and never exist at the same time. -->
    <AppIconButton
      icon="add"
      tooltip="New connection"
      data-testid="add-connector"
      @click="workspace.editConnector(null)"
    />
    <q-separator class="connector-rail__rule" />

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
/* A hairline under the plus: making a connection and reaching one already
   made are two different things, and at this width nothing else says so. */
.connector-rail__rule {
  width: 24px;
  margin: 2px 0 4px;
}
.connector-rail__slot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}
.connector-rail__slot--selected {
  background: var(--dp-selected);
}
/* On the icon rather than beside it: there is no room for a second column. */
.connector-rail__dot {
  position: absolute;
  right: 1px;
  bottom: 1px;
  border: 1px solid var(--dp-surface);
  pointer-events: none;
}
</style>
