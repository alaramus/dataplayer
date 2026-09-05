<script setup lang="ts">
import { useTemplateRef } from "vue"

import StructureView from "@/features/structure/StructureView.vue"
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
  <div class="structure-panel">
    <!-- A row of one group: the view below is a stack of sections and offers
         nothing about the panel itself, so what the panel offers stands on a
         line of its own (D112). -->
    <div class="structure-panel__bar">
      <PanelCommands
        :panel-id="panelId"
        :reveal="{ connectorId, nodeId, label: title }"
      />
    </div>
    <StructureView
      ref="view"
      class="structure-panel__view"
      :connector-id="connectorId"
      :node-id="nodeId"
    />
  </div>
</template>

<style scoped>
.structure-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
}
.structure-panel__view {
  flex: 1;
  min-height: 0;
}
.structure-panel__bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex: none;
  gap: 2px;
}
</style>
