<script setup lang="ts">
import { AxiosError } from "axios"
import { ref, watch } from "vue"

import type { FetchResult, Sort } from "@/client"
import { useFetchRows } from "@/features/catalog/api"
import { displayValue, toGridColumns, toGridRows } from "@/features/catalog/rows"
import type { GridColumn } from "@/features/catalog/rows"

const props = defineProps<{
  connectorId: string
  nodeId: string
  /** Approximate row count from the catalog node, when it has one. */
  rowEstimate?: number | null
}>()

const PAGE_SIZE = 50

const fetchRows = useFetchRows()

const columns = ref<GridColumn[]>([])
const rows = ref<Record<string, unknown>[]>([])
const page = ref(0)
const hasMore = ref(false)
// What the source said it can do in its last answer. A file has no index to
// order by, so the header must stop inviting a click the server will refuse.
const sortable = ref(true)
const sort = ref<Sort[]>([])
const error = ref("")

function messageOf(cause: unknown): string {
  if (cause instanceof AxiosError) {
    const detail = cause.response?.data?.detail
    if (detail && typeof detail === "object" && "message" in detail) {
      return String(detail.message)
    }
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  }
  return "Could not read the rows"
}

async function load() {
  error.value = ""
  try {
    const result: FetchResult = await fetchRows.mutateAsync({
      connectorId: props.connectorId,
      request: {
        node_id: props.nodeId,
        limit: PAGE_SIZE,
        offset: page.value * PAGE_SIZE,
        sort: sort.value,
        filters: [],
      },
    })
    columns.value = toGridColumns(result)
    rows.value = toGridRows(result)
    hasMore.value = result.has_more
    sortable.value = result.sortable !== false
  } catch (cause) {
    error.value = messageOf(cause)
    columns.value = []
    rows.value = []
    hasMore.value = false
  }
}

function sortBy(column: string) {
  if (!sortable.value) return
  const current = sort.value[0]
  sort.value =
    current && current.column === column && !current.descending
      ? [{ column, descending: true }]
      : [{ column, descending: false }]
  page.value = 0
  void load()
}

function turnPage(delta: number) {
  page.value = Math.max(0, page.value + delta)
  void load()
}

watch(
  () => [props.connectorId, props.nodeId],
  () => {
    page.value = 0
    sort.value = []
    void load()
  },
  { immediate: true }
)
</script>

<template>
  <div data-testid="row-grid">
    <q-banner
      v-if="error"
      dense
      class="bg-negative text-white q-mb-md"
      data-testid="grid-error"
    >
      {{ error }}
    </q-banner>

    <q-table
      v-else
      :rows="rows"
      :columns="columns"
      :loading="fetchRows.isPending.value"
      row-key="__index"
      flat
      bordered
      dense
      hide-pagination
      :rows-per-page-options="[0]"
      no-data-label="No rows"
    >
      <template #header-cell="cellProps">
        <q-th
          :props="cellProps"
          :class="{ 'cursor-pointer': sortable }"
          @click="sortBy(cellProps.col.name)"
        >
          {{ cellProps.col.label }}
          <q-icon
            v-if="sort[0]?.column === cellProps.col.name"
            :name="sort[0]?.descending ? 'arrow_downward' : 'arrow_upward'"
            size="14px"
          />
        </q-th>
      </template>

      <template #body-cell="cellProps">
        <q-td :props="cellProps">
          <span :class="{ 'text-grey': cellProps.value === null }">
            {{ displayValue(cellProps.value) }}
          </span>
        </q-td>
      </template>
    </q-table>

    <div class="row items-center justify-end q-gutter-sm q-mt-sm">
      <div class="text-caption text-grey">
        Rows {{ page * PAGE_SIZE + 1 }}–{{ page * PAGE_SIZE + rows.length }}
        <template v-if="rowEstimate !== null && rowEstimate !== undefined">
          of ~{{ rowEstimate }}
        </template>
      </div>
      <q-btn
        dense
        flat
        icon="chevron_left"
        :disable="page === 0"
        data-testid="grid-prev"
        @click="turnPage(-1)"
      />
      <q-btn
        dense
        flat
        icon="chevron_right"
        :disable="!hasMore"
        data-testid="grid-next"
        @click="turnPage(1)"
      />
    </div>
  </div>
</template>
