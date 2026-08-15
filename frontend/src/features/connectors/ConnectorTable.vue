<script setup lang="ts">
import type { ConnectorPublic } from "@/client"

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

const columns = [
  { name: "name", label: "Name", field: "name", align: "left" as const, sortable: true },
  { name: "adapter_type", label: "Type", field: "adapter_type", align: "left" as const },
  { name: "host", label: "Host", field: "host", align: "left" as const },
  { name: "actions", label: "", field: "actions", align: "right" as const },
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
  <q-table
    :rows="rows"
    :columns="columns"
    :loading="loading"
    row-key="id"
    flat
    bordered
    data-testid="connector-table"
    no-data-label="No connections yet"
  >
    <template #body-cell-host="cellProps">
      <q-td :props="cellProps">
        {{ hostOf(cellProps.row) }}
      </q-td>
    </template>

    <template #body-cell-adapter_type="cellProps">
      <q-td :props="cellProps">
        <q-badge
          color="primary"
          :label="cellProps.row.adapter_type"
        />
      </q-td>
    </template>

    <template #body-cell-actions="cellProps">
      <q-td
        :props="cellProps"
        class="q-gutter-xs"
      >
        <q-btn
          dense
          flat
          icon="account_tree"
          :data-testid="`browse-${cellProps.row.name}`"
          @click="$emit('browse', cellProps.row)"
        >
          <q-tooltip>Browse catalog</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="bolt"
          :data-testid="`check-${cellProps.row.name}`"
          @click="$emit('check', cellProps.row)"
        >
          <q-tooltip>Check connection</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="edit"
          :data-testid="`edit-${cellProps.row.name}`"
          @click="$emit('edit', cellProps.row)"
        >
          <q-tooltip>Edit</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="delete"
          color="negative"
          :data-testid="`delete-${cellProps.row.name}`"
          @click="$emit('remove', cellProps.row)"
        >
          <q-tooltip>Delete</q-tooltip>
        </q-btn>
      </q-td>
    </template>
  </q-table>
</template>
