<script setup lang="ts">
import { computed } from "vue"

import ConnectorList from "@/features/connectors/ConnectorList.vue"
import { useConnectors } from "@/features/connectors/api"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"

const workspace = useWorkspaceActions()
const connectors = useConnectors()

// The only panel whose whole content is one query, so re-reading it is asking
// vue-query again and nothing more.
useReloadable("connectors", async () => {
  await connectors.refetch()
})

const rows = computed(() => connectors.data.value?.data ?? [])
const filteredRows = computed(() => {
  const query = workspace.connectorNameFilter.value.trim().toLocaleLowerCase()
  return query
    ? rows.value.filter((connector) => connector.name.toLocaleLowerCase().includes(query))
    : rows.value
})
</script>

<template>
  <div
    class="connectors-panel"
    data-testid="connectors-panel"
  >
    <!-- Making a connection and re-reading the list stand in the head of the
         column, in place of its tab (ConnectorsHead). -->
    <div class="connectors-panel__body">
      <!-- Services used to stand above this list. They are a person's rather
           than a connection's, and this column is where every connection
           goes, so they moved into the panel at the foot of the screen
           (D143). -->
      <ConnectorList
        :rows="filteredRows"
        :empty-text="workspace.connectorNameFilter.value.trim() ? 'No matching connections' : undefined"
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
.connectors-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
/* The same four pixels under the head the rail of a collapsed column leaves,
   so the first icon does not move when the column is pushed aside. */
.connectors-panel__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-top: var(--dp-space-1);
}
</style>
