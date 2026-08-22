<script setup lang="ts">
import { computed, ref } from "vue"

import type { ConnectorPublic } from "@/client"
import CatalogDialog from "@/features/catalog/CatalogDialog.vue"
import ConnectorDialog from "@/features/connectors/ConnectorDialog.vue"
import ConnectorTable from "@/features/connectors/ConnectorTable.vue"
import { useCheckConnector, useConnectors, useDeleteConnector } from "@/features/connectors/api"
import { AppButton, AppLayout, AppPageHeader, useConfirm, useToast } from "@/shared/ui"

const confirm = useConfirm()
const toast = useToast()
const connectors = useConnectors()
const removeConnector = useDeleteConnector()
const checkConnector = useCheckConnector()

const dialogOpen = ref(false)
const editing = ref<ConnectorPublic | null>(null)
const catalogOpen = ref(false)
const browsing = ref<ConnectorPublic | null>(null)

const rows = computed(() => connectors.data.value?.data ?? [])

function openCreate() {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(connector: ConnectorPublic) {
  editing.value = connector
  dialogOpen.value = true
}

function openCatalog(connector: ConnectorPublic) {
  browsing.value = connector
  catalogOpen.value = true
}

async function check(connector: ConnectorPublic) {
  const result = await checkConnector.mutateAsync(connector.id)
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
  toast.success("Connection deleted")
}
</script>

<template>
  <AppLayout>
    <AppPageHeader title="Connections">
      <template #actions>
        <AppButton
          icon="add"
          label="New connection"
          data-testid="add-connector"
          @click="openCreate"
        />
      </template>
    </AppPageHeader>

    <ConnectorTable
      :rows="rows"
      :loading="connectors.isLoading.value"
      @edit="openEdit"
      @remove="confirmRemove"
      @check="check"
      @browse="openCatalog"
    />

    <ConnectorDialog
      v-model="dialogOpen"
      :connector="editing"
    />
    <CatalogDialog
      v-model="catalogOpen"
      :connector="browsing"
    />
  </AppLayout>
</template>
