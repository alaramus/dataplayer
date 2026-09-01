<script setup lang="ts">
import ResultTable from "@/features/queries/ResultTable.vue"

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
defineProps<{ panelId: string; resultId: string; title: string }>()
</script>

<template>
  <ResultTable
    :result-id="resultId"
    :title="title"
    class="result-panel"
  />
</template>

<style scoped>
.result-panel {
  height: 100%;
  min-height: 0;
}
</style>
