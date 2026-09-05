<script setup lang="ts">
import type { FetchRequest, ReferencedRows } from "@/client"
import RecordView from "@/features/record/RecordView.vue"
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
  <RecordView
    :connector-id="connectorId"
    :node-id="nodeId"
    :describable="describable"
    :request="request"
    :index="index ?? 0"
    @follow="showReferenced"
  />
</template>
