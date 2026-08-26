<script setup lang="ts">
import { useTemplateRef } from "vue"

import StructureView from "@/features/structure/StructureView.vue"
import { useReloadable } from "@/features/workspace/reloadable"

const props = defineProps<{ panelId: string; connectorId: string; nodeId: string }>()
const view = useTemplateRef<{ reload: () => Promise<void> }>("view")

useReloadable(props.panelId, async () => {
  await view.value?.reload()
})
</script>

<template>
  <div class="structure-panel">
    <StructureView
      ref="view"
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
</style>
