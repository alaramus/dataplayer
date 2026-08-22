<script setup lang="ts">
import { computed } from "vue"

import ConnectorList from "@/features/connectors/ConnectorList.vue"
import { useConnectors } from "@/features/connectors/api"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppIconButton } from "@/shared/ui"

const workspace = useWorkspaceActions()
const connectors = useConnectors()

const rows = computed(() => connectors.data.value?.data ?? [])
</script>

<template>
  <div class="connectors-panel">
    <div class="connectors-panel__bar">
      <!-- No title: the tab above the panel already carries one, and saying
           it twice costs a line of a column that is a fifth of the screen.
           An icon and not a labelled button, for the same reason. -->
      <span class="connectors-panel__spacer" />
      <AppIconButton
        icon="add"
        tooltip="New connection"
        data-testid="add-connector"
        @click="workspace.editConnector(null)"
      />
    </div>

    <div class="connectors-panel__body">
      <ConnectorList
        :rows="rows"
        :loading="connectors.isLoading.value"
        :selected-id="workspace.activeConnectorId.value"
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
.connectors-panel__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 4px;
}
.connectors-panel__spacer {
  flex: 1;
}
.connectors-panel__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
