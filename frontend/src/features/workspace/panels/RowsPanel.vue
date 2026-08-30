<script setup lang="ts">
import { ref, useTemplateRef, watch } from "vue"

import type { FetchRequest, ReferencedRows } from "@/client"
import DataGrid from "@/features/grid/DataGrid.vue"
import type { Filter } from "@/features/grid/types"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"

/**
 * One relation, in its own tab.
 *
 * The row estimate is not passed on: it belongs to the catalog node, and a
 * panel restored from storage has not read the catalog. The grid pages by
 * has_more when it has no estimate, which is what a file source gives it too.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  describable: boolean
}>()
const workspace = useWorkspaceActions()

const grid = useTemplateRef<{ reload: () => Promise<void> }>("grid")

useReloadable(props.panelId, async () => {
  await grid.value?.reload()
})

/**
 * The predicate this tab was navigated to by, once.
 *
 * Watched rather than received as a prop of the panel: the workspace binds a
 * panel's props when the panel is first drawn and keeps that binding, so a
 * tab already open would never see a second arrival. Taken from the workspace
 * for the same reason `revealTarget` is — see the note there.
 */
const referenceFilters = ref<Filter[] | null>(null)

watch(
  workspace.followTarget,
  () => {
    const taken = workspace.takeFollow(props.connectorId, props.nodeId)
    if (taken !== null) referenceFilters.value = [...taken.filters]
  },
  { immediate: true }
)

function showStructure() {
  workspace.openStructure({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
  })
}

function showChart(request: FetchRequest, columns: string[]) {
  workspace.openChart({
    connectorId: props.connectorId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    request,
    columns,
  })
}

function showReferenced(target: ReferencedRows) {
  workspace.followReference({
    connectorId: props.connectorId,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    target,
  })
}
</script>

<template>
  <div class="rows-panel">
    <DataGrid
      ref="grid"
      :connector-id="connectorId"
      :node-id="nodeId"
      :title="title"
      :can-describe="describable"
      :reference-filters="referenceFilters"
      @describe="showStructure"
      @chart="showChart"
      @follow="showReferenced"
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
