<script setup lang="ts">
import { useTemplateRef } from "vue"

import ResultTable from "@/features/queries/ResultTable.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"

/**
 * One captured result, in a panel of its own (D65).
 *
 * Two runs are two panels even when their SQL is the same: comparing them is
 * what the workspace's existing split and drag already do, so there is no
 * data-diff language here and no third thing to learn.
 *
 * A result does not survive a restart of the server. When it has gone the
 * table says so, and the run that produced it — which is durable — is still in
 * history.
 */
const props = defineProps<{ panelId: string; resultId: string; title: string }>()
const table = useTemplateRef<{ reload: () => Promise<void> }>("table")

useReloadable(props.panelId, async () => {
  await table.value?.reload()
})
</script>

<template>
  <ResultTable
    ref="table"
    :result-id="resultId"
    :title="title"
    class="result-panel"
  >
    <!-- No way back to a catalog: a captured result outlives the query that
         made it and names no node of any source (D112). -->
    <template #commands-end>
      <PanelCommands :panel-id="panelId" />
    </template>
  </ResultTable>
</template>

<style scoped>
.result-panel {
  height: 100%;
  min-height: 0;
}
</style>
