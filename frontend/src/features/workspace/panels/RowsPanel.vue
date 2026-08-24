<script setup lang="ts">
import { useTemplateRef } from "vue"

import RowGrid from "@/features/catalog/RowGrid.vue"
import { useReloadable } from "@/features/workspace/reloadable"

/**
 * One relation, in its own tab.
 *
 * The row estimate is not passed on: it belongs to the catalog node, and a
 * panel restored from storage has not read the catalog. The grid pages by
 * has_more when it has no estimate, which is what a file source gives it too.
 */
const props = defineProps<{ panelId: string; connectorId: string; nodeId: string }>()

const grid = useTemplateRef<{ reload: () => Promise<void> }>("grid")

useReloadable(props.panelId, async () => {
  await grid.value?.reload()
})
</script>

<template>
  <div class="rows-panel">
    <RowGrid
      ref="grid"
      :connector-id="connectorId"
      :node-id="nodeId"
    />
  </div>
</template>

<style scoped>
/* A box of the height the section gave it: the grid keeps its own header and
   its pager still and scrolls the rows between them. See the spec, S10. */
.rows-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
}
</style>
