<script setup lang="ts">
import { tableFeatures, useTable } from "@tanstack/vue-table"
import type { ColumnDef } from "@tanstack/vue-table"
import { computed, ref, toRef, watch } from "vue"

import type { Sort } from "@/client"
import { AppIconButton } from "@/shared/ui"

import { useRowsPage } from "./api"
import GridHeader from "./GridHeader.vue"
import { toGridRows } from "./model"
import {
  loadGridState,
  loadPageSize,
  reconcileGridState,
  saveGridState,
  savePageSize,
} from "./persist"
import { buildFetchRequest, withFilters, withPage, withPageSize } from "./queryState"
import { withSort } from "./queryState"
import { toggleMultiSort, toggleSingleSort } from "./sortModel"
import type { Filter, GridQueryState, GridRow, PageSize, StoredGridState } from "./types"

const props = defineProps<{ connectorId: string; nodeId: string }>()

const queryState = ref<GridQueryState>({
  page: 0,
  pageSize: loadPageSize(),
  filters: [],
  sort: [],
})
const request = computed(() => buildFetchRequest(props.nodeId, queryState.value))
const rowsQuery = useRowsPage(toRef(props, "connectorId"), request)
const result = computed(() => rowsQuery.data.value)
const rows = computed(() =>
  result.value === undefined ? [] : toGridRows(result.value, request.value.offset ?? 0)
)
const features = tableFeatures({})
type GridFeatures = typeof features
const columns = computed<ColumnDef<GridFeatures, GridRow>[]>(() =>
  (result.value?.columns ?? []).map((column, index) => ({
    id: column.name,
    header: column.name,
    accessorFn: (row) => row.values[index],
  }))
)

const table = useTable<GridFeatures, GridRow>({
  features,
  columns,
  data: rows,
  getRowId: (row) => row.id,
})

const offset = computed(() => queryState.value.page * queryState.value.pageSize)
const range = computed(() => {
  if (rows.value.length === 0) return "Rows 0"
  return `Rows ${offset.value + 1}–${offset.value + rows.value.length}`
})

function turnPage(delta: number) {
  queryState.value = withPage(queryState.value, Math.max(0, queryState.value.page + delta))
}

function changePageSize(pageSize: PageSize) {
  queryState.value = withPageSize(queryState.value, pageSize)
  savePageSize(pageSize)
}

function changeFilters(filters: Filter[]) {
  const next = withFilters(queryState.value, filters)
  queryState.value = next
  saveQueryState(next)
}

function changeSort(sort: Sort[]) {
  const next = withSort(queryState.value, sort)
  queryState.value = next
  saveQueryState(next)
}

function saveQueryState(state: GridQueryState) {
  const columns = result.value?.columns ?? []
  const stored = loadGridState(props.connectorId, props.nodeId)
  const base: StoredGridState =
    stored === null
      ? {
          columnOrder: columns.map((column) => column.name),
          columnVisibility: {},
          columnSizing: {},
          pinnedLeft: [],
          filters: [],
          sort: [],
        }
      : reconcileGridState(stored, columns)
  saveGridState(props.connectorId, props.nodeId, {
    ...base,
    filters: state.filters,
    sort: state.sort,
  })
}

function sortColumn(columnName: string, event: MouseEvent) {
  const column = result.value?.columns.find((candidate) => candidate.name === columnName)
  if (column?.sortable !== true) return
  changeSort(
    event.shiftKey
      ? toggleMultiSort(queryState.value.sort, columnName)
      : toggleSingleSort(queryState.value.sort, columnName)
  )
}

function sortIndex(columnName: string): number {
  return queryState.value.sort.findIndex((item) => item.column === columnName)
}

function displayCell(value: unknown): string {
  return value === null ? "∅" : String(value)
}

watch(
  () => [props.connectorId, props.nodeId],
  () => {
    queryState.value = withPage(queryState.value, 0)
  }
)

defineExpose({
  reload: async () => {
    await rowsQuery.refetch()
  },
})
</script>

<template>
  <div
    class="data-grid"
    data-testid="row-grid"
  >
    <GridHeader
      :page-size="queryState.pageSize"
      :columns="result?.columns ?? []"
      :filters="queryState.filters"
      :sort="queryState.sort"
      @update:page-size="changePageSize"
      @update:filters="changeFilters"
      @update:sort="changeSort"
    />

    <div class="data-grid__scroll">
      <table
        class="data-grid__table"
        role="grid"
      >
        <thead>
          <tr
            v-for="headerGroup in table.getHeaderGroups()"
            :key="headerGroup.id"
          >
            <th
              v-for="header in headerGroup.headers"
              :key="header.id"
              scope="col"
              :data-testid="`grid-column-${header.column.id}`"
              :class="{ 'data-grid__sortable': result?.columns.find((column) => column.name === header.column.id)?.sortable === true }"
              @click="sortColumn(header.column.id, $event)"
            >
              <span>{{ header.column.id }}</span>
              <template v-if="sortIndex(header.column.id) >= 0">
                <q-icon
                  :name="queryState.sort[sortIndex(header.column.id)]?.descending === true ? 'arrow_downward' : 'arrow_upward'"
                  :data-direction="queryState.sort[sortIndex(header.column.id)]?.descending === true ? 'desc' : 'asc'"
                  :data-testid="`grid-sort-direction-${header.column.id}`"
                  size="14px"
                />
                <span :data-testid="`grid-sort-priority-${header.column.id}`">
                  {{ sortIndex(header.column.id) + 1 }}
                </span>
              </template>
              <AppIconButton
                icon="more_horiz"
                :tooltip="`Select column ${header.column.id}`"
                :data-testid="`grid-column-select-${header.column.id}`"
                @click.stop
              />
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in table.getRowModel().rows"
            :key="row.id"
            :data-testid="`grid-row-${row.id}`"
          >
            <td
              v-for="cell in row.getAllCells()"
              :key="cell.id"
              :data-testid="`grid-cell-${row.id}-${cell.column.id}`"
            >
              {{ displayCell(cell.getValue()) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="data-grid__pager">
      <span data-testid="grid-page-range">{{ range }}</span>
      <AppIconButton
        icon="chevron_left"
        tooltip="Previous page"
        :disable="queryState.page === 0"
        data-testid="grid-prev"
        @click="turnPage(-1)"
      />
      <AppIconButton
        icon="chevron_right"
        tooltip="Next page"
        :disable="result?.has_more !== true"
        data-testid="grid-next"
        @click="turnPage(1)"
      />
    </div>
  </div>
</template>

<style scoped>
.data-grid {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  color: inherit;
}

.data-grid__scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.data-grid__table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
}

.data-grid__table th,
.data-grid__table td {
  min-width: 96px;
  padding: 6px 10px;
  border-right: 1px solid var(--dp-border-faint);
  border-bottom: 1px solid var(--dp-border-faint);
  text-align: left;
  white-space: nowrap;
}

.data-grid__table th {
  background: var(--dp-surface-raised);
  color: var(--dp-text-strong);
}

.data-grid__sortable {
  cursor: pointer;
}

.data-grid__pager {
  display: flex;
  flex: none;
  min-height: 40px;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  color: var(--dp-text-muted);
}
</style>
