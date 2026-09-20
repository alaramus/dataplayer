<script setup lang="ts">
import { useTemplateRef } from "vue"

import type { RelatedView } from "@/client"
import SummaryView from "@/features/summary/SummaryView.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
}>()
const workspace = useWorkspaceActions()
const view = useTemplateRef<{ reload: () => Promise<void> }>("view")

useReloadable(() => props.panelId, async () => {
  await view.value?.reload()
})

function openRelated(view: RelatedView) {
  workspace.followReference({
    connectorId: props.connectorId,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    target: {
      kind: "rows",
      node: { ...view.node, kind: "report" },
      filters: view.filters ?? [],
    },
  })
}
</script>

<template>
  <div class="summary-panel">
    <div class="summary-panel__bar">
      <PanelCommands
        :panel-id="panelId"
        :reveal="{ connectorId, nodeId, label: title }"
      />
    </div>
    <SummaryView
      ref="view"
      class="summary-panel__view"
      :connector-id="connectorId"
      :node-id="nodeId"
      @open-related="openRelated"
    />
  </div>
</template>

<style scoped>
.summary-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.summary-panel__view {
  flex: 1;
  min-height: 0;
}
.summary-panel__bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex: none;
  gap: var(--dp-space-half);
}
</style>
