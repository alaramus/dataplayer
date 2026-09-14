<script setup lang="ts">
import { computed } from "vue"

import { messageOf } from "@/shared/api/errors"
import { AppSelect, AppSpinner, AppTable, AppTooltip } from "@/shared/ui"
import type { TableColumns } from "@/shared/ui"

import type { ProcessInfo } from "@/client"

import { useProcesses } from "./api"
import { PROCESS_LIMITS, PROCESS_SORTS } from "./dashboardModel"
import type { ProcessLimit, ProcessSort } from "./dashboardModel"
import { commandWording, runningForWording, stateWording } from "./hostFacts"
import { formatValue } from "./seriesFormat"

/** The newest process table one host sent, sorted and cut the way it was asked. */
const props = defineProps<{
  agentId: string
  host: string
  sort: ProcessSort
  limit: ProcessLimit
  refreshSeconds: number
  dashboardId: string | null
}>()

const emit = defineEmits<{ options: [patch: { sort?: ProcessSort; limit?: ProcessLimit }] }>()

const table = useProcesses(
  () => props.agentId,
  () => props.host,
  () => props.sort,
  () => props.limit,
  () => props.refreshSeconds,
  () => props.dashboardId
)

const columns: TableColumns = [
  { name: "pid", label: "PID", field: "pid", align: "right" },
  { name: "user", label: "User", field: "user", align: "left" },
  { name: "state", label: "S", field: "state", align: "left" },
  { name: "pcpu", label: "%CPU", field: "pcpu", align: "right" },
  { name: "pmem", label: "%MEM", field: "pmem", align: "right" },
  { name: "rss", label: "Resident", field: (row: ProcessInfo) => formatValue(row.rss_bytes, "B"), align: "right" },
  { name: "running", label: "Running for", field: (row: ProcessInfo) => runningForWording(row, table.dataUpdatedAt.value), align: "left" },
  { name: "command", label: "Command", field: (row: ProcessInfo) => commandWording(row), align: "left" },
]

const rows = computed(() => table.data.value?.rows ?? [])
const taken = computed(() => {
  const answer = table.data.value
  if (answer?.ts === null || answer?.ts === undefined) return null
  const at = `As of ${new Date(answer.ts * 1000).toLocaleTimeString()}`
  return answer.total === null || answer.total === undefined ? at : `${at} · ${String(answer.total)} processes on the host`
})
const failure = computed(() =>
  table.isError.value ? messageOf(table.error.value, "The process table could not be read") : null
)
</script>

<template>
  <div
    class="processes-widget"
    data-testid="processes-widget"
  >
    <div class="processes-widget__bar">
      <span class="processes-widget__note">{{ taken ?? "" }}</span>
      <AppSelect
        :model-value="sort"
        :options="PROCESS_SORTS"
        compact
        aria-label="Sort processes"
        @update:model-value="(value) => emit('options', { sort: value as ProcessSort })"
      />
      <AppSelect
        :model-value="limit"
        :options="PROCESS_LIMITS"
        compact
        aria-label="Rows"
        @update:model-value="(value) => emit('options', { limit: value as ProcessLimit })"
      />
    </div>
    <div
      v-if="failure"
      class="processes-widget__center"
    >
      {{ failure }}
    </div>
    <div
      v-else-if="table.isPending.value"
      class="processes-widget__center"
    >
      <AppSpinner />
    </div>
    <div
      v-else-if="table.data.value?.ts === null"
      class="processes-widget__center"
    >
      No process table in the last hour
    </div>
    <div
      v-else
      class="processes-widget__table"
    >
      <AppTable
        :rows="rows"
        :columns="columns"
        row-key="pid"
        compact
        sticky
        :paged="false"
      >
        <template #body-cell-state="cellProps">
          <q-td :props="cellProps">
            {{ cellProps.row.state }}
            <AppTooltip>{{ stateWording(cellProps.row.state) }}</AppTooltip>
          </q-td>
        </template>
      </AppTable>
    </div>
  </div>
</template>

<style scoped>
.processes-widget {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  height: 100%;
  min-height: 0;
}

.processes-widget__bar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.processes-widget__note {
  flex: 1;
  color: var(--dp-text-muted);
}

.processes-widget__table {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.processes-widget__center {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  color: var(--dp-text-muted);
}
</style>
