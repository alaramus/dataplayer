<script setup lang="ts">
import RowGrid from "@/features/catalog/RowGrid.vue"

/**
 * One relation, in its own tab.
 *
 * The row estimate is not passed on: it belongs to the catalog node, and a
 * panel restored from storage has not read the catalog. The grid pages by
 * has_more when it has no estimate, which is what a file source gives it too.
 */
defineProps<{ connectorId: string; nodeId: string }>()
</script>

<template>
  <div class="rows-panel">
    <RowGrid
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
