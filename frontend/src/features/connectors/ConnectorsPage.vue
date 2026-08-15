<script setup lang="ts">
import { useQuasar } from "quasar"
import { computed, ref } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorDialog from "@/features/connectors/ConnectorDialog.vue"
import ConnectorTable from "@/features/connectors/ConnectorTable.vue"
import { useCheckConnector, useConnectors, useDeleteConnector } from "@/features/connectors/api"
import AppLayout from "@/shared/ui/AppLayout.vue"

const quasar = useQuasar()
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
  quasar.notify({
    type: result.ok ? "positive" : "negative",
    message: result.ok ? `${result.message} (${String(result.latency_ms)} ms)` : result.message,
  })
}

function confirmRemove(connector: ConnectorPublic) {
  quasar
    .dialog({
      title: "Delete connection",
      message: `The connection "${connector.name}" will be deleted permanently.`,
      cancel: true,
      ok: { label: "Delete", color: "negative" },
    })
    .onOk(() => {
      void removeConnector.mutateAsync(connector.id).then(() => {
        quasar.notify({ type: "positive", message: "Connection deleted" })
      })
    })
}
</script>

<template>
  <AppLayout>
    <div class="row items-center justify-between q-mb-md">
      <div class="text-h5">
        Connections
      </div>
      <q-btn
        color="primary"
        icon="add"
        label="New connection"
        data-testid="add-connector"
        @click="openCreate"
      />
    </div>

    <ConnectorTable
      :rows="rows"
      :loading="connectors.isLoading.value"
      @edit="openEdit"
      @remove="confirmRemove"
      @check="check"
    />

    <ConnectorDialog
      v-model="dialogOpen"
      :connector="editing"
    />
  </AppLayout>
</template>
