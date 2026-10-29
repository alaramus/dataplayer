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

useReloadable(() => props.panelId, async () => {
  await view.value?.reload()
})
</script>

<template>
  <div class="structure-panel">
    <!-- A row of one group: the view below is a stack of sections and offers
         nothing about the panel itself, so what the panel offers stands on a
         line of its own (D112). -->
    <div class="structure-panel__bar">
      <!-- What the panel is about, where every other panel's head says it:
           the commands alone stood at the right of an empty line. -->
      <span class="structure-panel__title">{{ title }}</span>
      <PanelCommands
        :panel-id="panelId"
        :reveal="{ connectorId, nodeId, label: title }"
      />
    </div>
    <StructureView
      ref="view"
      class="structure-panel__view dp-panel-scroll"
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
  padding: var(--dp-space-1);
}
.structure-panel__view {
  flex: 1;
  min-height: 0;
}
.structure-panel__bar {
  display: flex;
  align-items: center;
  flex: none;
  gap: var(--dp-space-half);
}
.structure-panel__title {
  flex: 1;
  min-width: 0;
  padding-inline-start: var(--dp-space-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
</style>
