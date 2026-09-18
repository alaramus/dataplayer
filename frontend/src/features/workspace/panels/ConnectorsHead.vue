<script setup lang="ts">
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppIconButton } from "@/shared/ui"

/**
 * The head of the column of connections, where its tab used to be.
 *
 * The column holds nothing else and the panel can be neither closed nor
 * carried anywhere, so the tab only said "Connections". Making one on the
 * left, where the rail of a collapsed column keeps it, and re-reading the list
 * at the end, where every panel keeps what it offers about itself (D112).
 */
const workspace = useWorkspaceActions()
</script>

<template>
  <div
    class="connectors-head"
    role="toolbar"
    aria-label="Connections"
    data-testid="connectors-head"
  >
    <AppIconButton
      icon="add"
      tooltip="New connection"
      data-testid="add-connector"
      @click="workspace.editConnector(null)"
    />
    <span class="connectors-head__commands">
      <PanelCommands panel-id="connectors" />
    </span>
  </div>
</template>

<style scoped>
.connectors-head {
  display: flex;
  align-items: center;
  gap: 4px;
}
.connectors-head__commands {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}
</style>
