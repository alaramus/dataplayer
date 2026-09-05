<script setup lang="ts">
import { useTemplateRef } from "vue"

import SummaryView from "@/features/summary/SummaryView.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
}>()
const view = useTemplateRef<{ reload: () => Promise<void> }>("view")

useReloadable(props.panelId, async () => {
  await view.value?.reload()
})
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
    />
  </div>
</template>

<style scoped>
.summary-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
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
  gap: 2px;
}
</style>
