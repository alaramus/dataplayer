<script setup lang="ts">
import type { ConnectorPublic } from "@/client"
import { AppBadge, AppIconButton, AppTable } from "@/shared/ui"
import type { TableColumns } from "@/shared/ui/AppTable.vue"

defineProps<{
  rows: ConnectorPublic[]
  loading: boolean
}>()

defineEmits<{
  edit: [connector: ConnectorPublic]
  remove: [connector: ConnectorPublic]
  check: [connector: ConnectorPublic]
  browse: [connector: ConnectorPublic]
}>()

const columns: TableColumns = [
  { name: "name", label: "Name", field: "name", align: "left", sortable: true },
  { name: "adapter_type", label: "Type", field: "adapter_type", align: "left" },
  { name: "host", label: "Host", field: "host", align: "left" },
  { name: "actions", label: "", field: "actions", align: "right" },
]

function hostOf(connector: ConnectorPublic): string {
  const config = connector.config as Record<string, unknown>
  const host = config.host
  const port = config.port
  if (typeof host !== "string") return "—"
  return port === undefined ? host : `${host}:${String(port)}`
}
</script>

<template>
  <AppTable
    :rows="rows"
    :columns="columns"
    :loading="loading"
    row-key="id"
    data-testid="connector-table"
    empty-text="No connections yet"
  >
    <template #body-cell-host="cellProps">
      <q-td :props="cellProps">
        {{ hostOf(cellProps.row) }}
      </q-td>
    </template>

    <template #body-cell-adapter_type="cellProps">
      <q-td :props="cellProps">
        <AppBadge :label="cellProps.row.adapter_type" />
      </q-td>
    </template>

    <template #body-cell-actions="cellProps">
      <q-td
        :props="cellProps"
        class="q-gutter-xs"
      >
        <AppIconButton
          icon="account_tree"
          tooltip="Browse catalog"
          :data-testid="`browse-${cellProps.row.name}`"
          @click="$emit('browse', cellProps.row)"
        />
        <AppIconButton
          icon="bolt"
          tooltip="Check connection"
          :data-testid="`check-${cellProps.row.name}`"
          @click="$emit('check', cellProps.row)"
        />
        <AppIconButton
          icon="edit"
          tooltip="Edit"
          :data-testid="`edit-${cellProps.row.name}`"
          @click="$emit('edit', cellProps.row)"
        />
        <AppIconButton
          icon="delete"
          tooltip="Delete"
          variant="danger-quiet"
          :data-testid="`delete-${cellProps.row.name}`"
          @click="$emit('remove', cellProps.row)"
        />
      </q-td>
    </template>
  </AppTable>
</template>
