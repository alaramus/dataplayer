<script setup lang="ts">
import { computed, ref } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorDialog from "@/features/connectors/ConnectorDialog.vue"
import ConnectorList from "@/features/connectors/ConnectorList.vue"
import { useCheckConnector, useConnectors, useDeleteConnector } from "@/features/connectors/api"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppButton, useConfirm, useToast } from "@/shared/ui"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

const confirm = useConfirm()
const toast = useToast()
const workspace = useWorkspaceActions()
const checks = useConnectorChecksStore()
const connectors = useConnectors()
const removeConnector = useDeleteConnector()
const checkConnector = useCheckConnector()

const dialogOpen = ref(false)
const editing = ref<ConnectorPublic | null>(null)

const rows = computed(() => connectors.data.value?.data ?? [])

function openCreate() {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(connector: ConnectorPublic) {
  editing.value = connector
  dialogOpen.value = true
}

async function check(connector: ConnectorPublic) {
  const result = await checkConnector.mutateAsync(connector.id)
  checks.record(connector.id, result.ok)
  if (result.ok) {
    toast.success(`${result.message} (${String(result.latency_ms)} ms)`)
  } else {
    toast.error(result.message)
  }
}

async function confirmRemove(connector: ConnectorPublic) {
  const answer = await confirm({
    title: "Delete connection",
    message: `The connection "${connector.name}" will be deleted permanently.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!answer) return

  await removeConnector.mutateAsync(connector.id)
  // The dot outlives the row otherwise: an id can be reused by nothing, but a
  // record nobody prunes is a record that grows for as long as the page lives.
  checks.forget(connector.id)
  toast.success("Connection deleted")
}
</script>

<template>
  <div class="connectors-panel">
    <div class="connectors-panel__bar">
      <AppButton
        icon="add"
        size="sm"
        label="New connection"
        data-testid="add-connector"
        @click="openCreate"
      />
    </div>

    <ConnectorList
      :rows="rows"
      :loading="connectors.isLoading.value"
      :selected-id="workspace.activeConnectorId.value"
      @open="workspace.openCatalog($event.id, $event.name)"
      @edit="openEdit"
      @remove="confirmRemove"
      @check="check"
    />

    <ConnectorDialog
      v-model="dialogOpen"
      :connector="editing"
    />
  </div>
</template>

<style scoped>
.connectors-panel {
  padding: 8px 0;
}
.connectors-panel__bar {
  padding: 0 8px 8px;
}
</style>
