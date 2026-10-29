<script setup lang="ts">
import { useTemplateRef } from "vue"

import type { FetchRequest, ReferencedRows } from "@/client"
import RecordView from "@/features/record/RecordView.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"

/**
 * One row of one relation, in its own tab (D111).
 *
 * Which row is a field of the panel rather than a message to it: opening
 * another row of the same relation rewrites this panel, so a tab restored from
 * storage comes back on the row it was left on. A tab per row would fill the
 * strip by reading a table.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  describable: boolean
  /** Absent in a layout stored before a row view had one; see below. */
  request?: FetchRequest
  index?: number
}>()
const workspace = useWorkspaceActions()
const view = useTemplateRef<{ reload: () => Promise<void> }>("view")

useReloadable(() => props.panelId, async () => {
  await view.value?.reload()
})

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
  <div class="record-panel">
    <div class="record-panel__bar">
      <!-- What the panel is about, where every other panel's head says it:
           the commands alone stood at the right of an empty line. -->
      <span class="record-panel__title">{{ title }}</span>
      <PanelCommands
        :panel-id="panelId"
        :reveal="{ connectorId, nodeId, label: title }"
      />
    </div>
    <RecordView
      ref="view"
      class="record-panel__view"
      :connector-id="connectorId"
      :node-id="nodeId"
      :describable="describable"
      :request="request"
      :index="index ?? 0"
      @follow="showReferenced"
    />
  </div>
</template>

<style scoped>
.record-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.record-panel__view {
  flex: 1;
  min-height: 0;
}
.record-panel__bar {
  display: flex;
  align-items: center;
  flex: none;
  gap: var(--dp-space-half);
}
.record-panel__title {
  flex: 1;
  min-width: 0;
  padding-inline-start: var(--dp-space-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
</style>
