<script setup lang="ts">
import { computed } from "vue"

import ConnectorIcon from "@/features/connectors/ConnectorIcon.vue"
import { useConnectors } from "@/features/connectors/api"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppIconButton } from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"

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
        'connector-rail__slot--open': workspace.openConnectorIds.value.has(connector.id),
        'connector-rail__slot--selected': connector.id === workspace.activeConnectorId.value,
      }"
      :style="panelColorStyle(connector.tab_color)"
    >
      <ConnectorIcon
        :connector-id="connector.id"
        :name="connector.name"
        :adapter-type="connector.adapter_type"
        :enabled="connector.enabled"
        :tooltip="connector.name"
        :testid="`connector-rail-${connector.name}`"
        @click="workspace.openCatalog(connector)"
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
   made are two different things. It stretches to whatever width the column
   has, which is how the wide list draws the same rule without a second
   declaration of it. */
.connector-rail__rule {
  align-self: stretch;
  margin: 2px 8px 4px;
}
.connector-rail__slot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}
/* The same two states the wide row carries, at a smaller width — and in the
   connection's own colour for the same reason: pushing the column aside takes
   away the name and nothing else. */
.connector-rail__slot--open {
  background: var(--dp-panel-quiet, var(--dp-panel-plain-quiet));
}
.connector-rail__slot--selected {
  background: var(--dp-panel-background, var(--dp-panel-plain));
}
</style>
