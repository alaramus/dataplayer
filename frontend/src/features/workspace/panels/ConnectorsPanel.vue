<script setup lang="ts">
import { computed } from "vue"

import ConnectorList from "@/features/connectors/ConnectorList.vue"
import { useConnectors } from "@/features/connectors/api"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppIconButton } from "@/shared/ui"

const workspace = useWorkspaceActions()
const connectors = useConnectors()

// The only panel whose whole content is one query, so re-reading it is asking
// vue-query again and nothing more.
useReloadable("connectors", async () => {
  await connectors.refetch()
})

const rows = computed(() => connectors.data.value?.data ?? [])
</script>

<template>
  <div
    class="connectors-panel"
    data-testid="connectors-panel"
  >
    <div class="connectors-panel__bar">
      <!-- No title: the tab above the panel already carries one, and a column
           a fifth of the screen wide cannot spend a line saying it twice. An
           icon and not a labelled button, for the same reason.

           On the left, where the strip a collapsed column leaves behind puts
           it: pushing the column aside takes the name away and moves nothing.

           Queries used to stand here for want of anywhere better; they are a
           command of a connection and live in the bar at the foot now (D69). -->
      <AppIconButton
        icon="add"
        tooltip="New connection"
        data-testid="add-connector"
        @click="workspace.editConnector(null)"
      />
      <!-- At the end of the row, where every panel keeps what it offers about
           itself. The list of connections is nobody's node, so re-reading it
           is the only thing here (D112). -->
      <div class="connectors-panel__commands">
        <PanelCommands panel-id="connectors" />
      </div>
    </div>
    <q-separator class="connectors-panel__rule" />

    <div class="connectors-panel__body">
      <!-- Services used to stand above this list. They are a person's rather
           than a connection's, and this column is where every connection
           goes, so they moved into the panel at the foot of the screen
           (D143). -->
      <ConnectorList
        :rows="rows"
        :loading="connectors.isLoading.value"
        :selected-id="workspace.activeConnectorId.value"
        :open-ids="workspace.openConnectorIds.value"
        @open="workspace.openCatalog"
        @edit="workspace.editConnector($event.id)"
      />
    </div>
  </div>
</template>

<style scoped>
/* A box of the height the section gave it: the bar stays, the list moves. */
.connectors-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
/* Four pixels of padding, which is exactly where a forty-pixel strip centres
   a thirty-two pixel button: the plus does not move when the column is pushed
   aside. */
.connectors-panel__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 0 0 4px;
}
/* The same hairline the strip draws, at the width this column happens to
   have. */
.connectors-panel__commands {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}
.connectors-panel__rule {
  flex: none;
  margin: 2px 8px 4px;
}
.connectors-panel__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
