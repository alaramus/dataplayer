<script setup lang="ts">
import {
  columnOrderingFeature,
  columnPinningFeature,
  columnResizingFeature,
  columnSizingFeature,
  columnVisibilityFeature,
  functionalUpdate,
  tableFeatures,
  useTable,
} from "@tanstack/vue-table"
import type { Column, ColumnDef, ColumnPinningState, Updater } from "@tanstack/vue-table"
import { computed, ref, toRef, watch } from "vue"
import type { CSSProperties } from "vue"

import type { Sort } from "@/client"
import { AppIconButton } from "@/shared/ui"

import { useRowsPage } from "./api"
import { autoFitWidth, defaultColumnLayout } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"
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

const EMPTY_LAYOUT: ColumnLayoutState = {
  columnOrder: [],
  columnVisibility: {},
  columnSizing: {},
  pinnedLeft: [],
}

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
const layout = ref<ColumnLayoutState>({ ...EMPTY_LAYOUT })
const selectedColumn = ref<string | null>(null)
const features = tableFeatures({
  columnSizingFeature,
  columnResizingFeature,
  columnOrderingFeature,
  columnVisibilityFeature,
  columnPinningFeature,
})
type GridFeatures = typeof features
const columns = computed<ColumnDef<GridFeatures, GridRow>[]>(() =>
  (result.value?.columns ?? []).map((column, index) => ({
    id: column.name,
    header: column.name,
    accessorFn: (row) => row.values[index],
    minSize: 72,
    maxSize: 480,
    size: 160,
  }))
)
const tableState = computed(() => ({
  columnOrder: layout.value.columnOrder,
  columnVisibility: layout.value.columnVisibility,
  columnSizing: layout.value.columnSizing,
  columnPinning: { start: layout.value.pinnedLeft, end: [] },
}))

const table = useTable<GridFeatures, GridRow>({
  features,
  columns,
  data: rows,
  getRowId: (row) => row.id,
  state: tableState,
  columnResizeMode: "onEnd",
  onColumnOrderChange: (updater) =>
    changeLayout({
      ...layout.value,
      columnOrder: functionalUpdate(updater, layout.value.columnOrder),
    }),
  onColumnVisibilityChange: (updater) =>
    changeLayout({
      ...layout.value,
      columnVisibility: functionalUpdate(updater, layout.value.columnVisibility),
    }),
  onColumnSizingChange: (updater) =>
    changeLayout({
      ...layout.value,
      columnSizing: functionalUpdate(updater, layout.value.columnSizing),
    }),
  onColumnPinningChange: (updater: Updater<ColumnPinningState>) => {
    const next = functionalUpdate(updater, { start: layout.value.pinnedLeft, end: [] })
    changeLayout({ ...layout.value, pinnedLeft: next.start })
  },
})

const columnWidthVariables = computed<Record<string, string>>(() =>
  Object.fromEntries(
    table.getAllLeafColumns().map((column) => [columnVariable(column.id), `${column.getSize()}px`])
  )
)

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

function changeLayout(next: ColumnLayoutState) {
  layout.value = next
  saveGridState(props.connectorId, props.nodeId, {
    ...next,
    filters: queryState.value.filters,
    sort: queryState.value.sort,
  })
}

function saveQueryState(state: GridQueryState) {
  const columns = result.value?.columns ?? []
  const stored = loadGridState(props.connectorId, props.nodeId)
  const base: StoredGridState =
    stored === null
      ? { ...defaultColumnLayout(columns), filters: [], sort: [] }
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

function columnVariable(columnName: string): string {
  const index = result.value?.columns.findIndex((column) => column.name === columnName) ?? -1
  return `--grid-column-${Math.max(0, index)}`
}

function columnStyle(column: Column<GridFeatures, GridRow, unknown>): CSSProperties {
  return {
    width: `var(${columnVariable(column.id)})`,
    insetInlineStart:
      column.getIsPinned() === "start" ? `${column.getStart("start")}px` : undefined,
  }
}

let textContext: CanvasRenderingContext2D | null | undefined
function measureFullText(text: string): number {
  if (textContext === undefined) {
    textContext =
      typeof CanvasRenderingContext2D === "undefined"
        ? null
        : document.createElement("canvas").getContext("2d")
    if (textContext !== null) textContext.font = "14px sans-serif"
  }
  return (textContext?.measureText(text).width ?? text.length * 8) + 32
}

function autoFit(columnName: string) {
  const resultValue = result.value
  if (resultValue === undefined) return
  const index = resultValue.columns.findIndex((column) => column.name === columnName)
  if (index === -1) return
  const values = resultValue.rows.map((row) => row[index] ?? null)
  const width = autoFitWidth(columnName, values, measureFullText, { min: 72, max: 480 })
  changeLayout({
    ...layout.value,
    columnSizing: { ...layout.value.columnSizing, [columnName]: width },
  })
}

function displayCell(value: unknown): string {
  return value === null ? "∅" : String(value)
}

let restoredKey = ""
watch(
  () => result.value?.columns,
  (serverColumns) => {
    if (serverColumns === undefined) return
    const key = `${props.connectorId}\u0000${props.nodeId}`
    if (restoredKey === key) return
    restoredKey = key

    const stored = loadGridState(props.connectorId, props.nodeId)
    if (stored === null) {
      layout.value = defaultColumnLayout(serverColumns)
      return
    }
    const reconciled = reconcileGridState(stored, serverColumns)
    layout.value = {
      columnOrder: reconciled.columnOrder,
      columnVisibility: reconciled.columnVisibility,
      columnSizing: reconciled.columnSizing,
      pinnedLeft: reconciled.pinnedLeft,
    }
    queryState.value = {
      ...queryState.value,
      page: 0,
      filters: reconciled.filters,
      sort: reconciled.sort,
    }
  },
  { immediate: true }
)

watch(
  () => [props.connectorId, props.nodeId],
  () => {
    restoredKey = ""
    selectedColumn.value = null
    layout.value = { ...EMPTY_LAYOUT }
    queryState.value = { ...withPage(queryState.value, 0), filters: [], sort: [] }
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
    :style="columnWidthVariables"
  >
    <GridHeader
      :page-size="queryState.pageSize"
      :columns="result?.columns ?? []"
      :filters="queryState.filters"
      :sort="queryState.sort"
      :layout="layout"
      :selected-column="selectedColumn"
      @update:page-size="changePageSize"
      @update:filters="changeFilters"
      @update:sort="changeSort"
      @update:layout="changeLayout"
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
              :class="{
                'data-grid__sortable': result?.columns.find((column) => column.name === header.column.id)?.sortable === true,
                'data-grid__pinned': header.column.getIsPinned() === 'start',
              }"
              :style="columnStyle(header.column)"
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
                @click.stop="selectedColumn = header.column.id"
              />
              <span
                class="data-grid__resize"
                :data-testid="`grid-resize-${header.column.id}`"
                @mousedown.stop="header.getResizeHandler()($event)"
                @touchstart.stop="header.getResizeHandler()($event)"
                @dblclick.stop="autoFit(header.column.id)"
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
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-testid="`grid-cell-${row.id}-${cell.column.id}`"
              :class="{ 'data-grid__pinned': cell.column.getIsPinned() === 'start' }"
              :style="columnStyle(cell.column)"
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
  position: relative;
  box-sizing: border-box;
  min-width: 0;
  max-width: none;
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

.data-grid__pinned {
  position: sticky !important;
  z-index: var(--dp-layer-sticky);
  background: var(--dp-surface-raised);
  box-shadow: 2px 0 3px var(--dp-shadow-soft);
}

.data-grid__resize {
  position: absolute;
  inset-block: 0;
  inset-inline-end: -3px;
  width: 6px;
  cursor: col-resize;
  touch-action: none;
  user-select: none;
}

.data-grid__resize:hover {
  background: var(--dp-separator-active);
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
