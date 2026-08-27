<script setup lang="ts">
import {
  columnOrderingFeature,
  columnPinningFeature,
  columnResizingFeature,
  columnSizingFeature,
  columnVisibilityFeature,
  cellSelectionFeature,
  functionalUpdate,
  tableFeatures,
  useTable,
} from "@tanstack/vue-table"
import type {
  Cell,
  CellSelectionDirection,
  Column,
  ColumnDef,
  ColumnPinningState,
  Updater,
} from "@tanstack/vue-table"
import { computed, ref, toRef, useTemplateRef, watch } from "vue"
import type { CSSProperties } from "vue"

import type { FetchColumn, Sort } from "@/client"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  useConfirm,
  useToast,
} from "@/shared/ui"

import { useDeleteRows, useInsertRow, useRowsPage, useUpdateCell } from "./api"
import CellEditorDialog from "./CellEditorDialog.vue"
import CellValueDialog from "./CellValueDialog.vue"
import { toTsv, writeSelection } from "./clipboard"
import { autoFitWidth, defaultColumnLayout } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"
import GridHeader from "./GridHeader.vue"
import RowInsertDialog from "./RowInsertDialog.vue"
import { cellPresentation, shouldOpenViewer, toGridRows } from "./model"
import type { CellPresentation } from "./model"
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
import { selectedWholeRowIndexes, selectionMatrix } from "./selection"
import type { VisibleGridColumn } from "./selection"
import type { Filter, GridQueryState, GridRow, PageSize, StoredGridState } from "./types"

const props = defineProps<{ connectorId: string; nodeId: string }>()
const toast = useToast()
const confirm = useConfirm()

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
  result.value === undefined || rowsQuery.isError.value
    ? []
    : toGridRows(result.value, request.value.offset ?? 0)
)
const layout = ref<ColumnLayoutState>({ ...EMPTY_LAYOUT })
const selectedColumn = ref<string | null>(null)
const viewer = ref<{ columnName: string; typeSql: string; value: string } | null>(null)
const editor = ref<{
  column: FetchColumn
  value: string | null
  rowHandle: string
} | null>(null)
const editError = ref("")
const insertOpen = ref(false)
const insertError = ref("")
const updateCell = useUpdateCell(toRef(props, "connectorId"))
const insertRow = useInsertRow(toRef(props, "connectorId"))
const deleteRows = useDeleteRows(toRef(props, "connectorId"))
const gridFocus = useTemplateRef<HTMLElement>("gridFocus")
const features = tableFeatures({
  columnSizingFeature,
  columnResizingFeature,
  columnOrderingFeature,
  columnVisibilityFeature,
  columnPinningFeature,
  cellSelectionFeature,
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
const canCopy = computed(() => table.getSelectedCellCount() > 0)
const visibleGridColumns = computed<VisibleGridColumn[]>(() => {
  const ordered = [
    ...table.getStartVisibleLeafColumns(),
    ...table.getCenterVisibleLeafColumns(),
  ]
  return ordered.flatMap((column) => {
    const valueIndex = result.value?.columns.findIndex((item) => item.name === column.id) ?? -1
    return valueIndex < 0 ? [] : [{ id: column.id, valueIndex }]
  })
})
const selectedRowIndexes = computed(() =>
  selectedWholeRowIndexes(
    table.getCellSelectionBounds(),
    visibleGridColumns.value.length
  )
)
const selectedRowHandles = computed(() => {
  const handles = result.value?.row_handles ?? []
  const selected = selectedRowIndexes.value.map((index) => handles[index])
  return selected.every((handle): handle is string => typeof handle === "string")
    ? selected
    : []
})
const canInsert = computed(() => result.value?.insert_supported === true)
const canDelete = computed(
  () =>
    result.value?.delete_supported === true &&
    selectedRowIndexes.value.length > 0 &&
    selectedRowHandles.value.length === selectedRowIndexes.value.length
)
const deleteReason = computed(() => {
  if (result.value?.delete_supported !== true) return result.value?.delete_reason ?? undefined
  if (selectedRowIndexes.value.length === 0) return "Select complete rows to delete"
  return selectedRowHandles.value.length === selectedRowIndexes.value.length
    ? undefined
    : "The selected rows cannot be deleted"
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

function changeLayout(next: ColumnLayoutState) {
  table.resetCellSelection(true)
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

function startSelection(cell: Cell<GridFeatures, GridRow, unknown>, event: MouseEvent) {
  gridFocus.value?.focus()
  cell.getSelectionStartHandler()(event)
}

function selectRow(rowId: string) {
  const columns = visibleGridColumns.value
  const first = columns[0]
  const last = columns.at(-1)
  if (first === undefined || last === undefined) return
  table.selectCellRange({
    anchorRowId: rowId,
    focusRowId: rowId,
    anchorColumnId: first.id,
    focusColumnId: last.id,
  })
}

function selectColumn(columnId: string) {
  selectedColumn.value = columnId
  const first = rows.value[0]
  const last = rows.value.at(-1)
  if (first === undefined || last === undefined) return
  table.selectCellRange({
    anchorRowId: first.id,
    focusRowId: last.id,
    anchorColumnId: columnId,
    focusColumnId: columnId,
  })
}

function selectPage() {
  const firstRow = rows.value[0]
  const lastRow = rows.value.at(-1)
  const firstColumn = visibleGridColumns.value[0]
  const lastColumn = visibleGridColumns.value.at(-1)
  if (
    firstRow === undefined ||
    lastRow === undefined ||
    firstColumn === undefined ||
    lastColumn === undefined
  ) {
    return
  }
  table.selectCellRange({
    anchorRowId: firstRow.id,
    focusRowId: lastRow.id,
    anchorColumnId: firstColumn.id,
    focusColumnId: lastColumn.id,
  })
}

async function copySelection() {
  const matrix = selectionMatrix(rows.value, visibleGridColumns.value, table.getCellSelectionBounds())
  if (matrix.length === 0) return
  try {
    await writeSelection(toTsv(matrix))
  } catch {
    toast.error("Could not copy the selection")
  }
}

function handleGridKey(event: KeyboardEvent) {
  const directions: Partial<Record<string, CellSelectionDirection>> = {
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
  }
  const direction = directions[event.key]
  if (direction !== undefined) {
    event.preventDefault()
    if (event.shiftKey) table.extendCellSelection(direction)
    else table.moveCellSelection(direction)
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
    event.preventDefault()
    void copySelection()
  }
}

function serverColumn(columnId: string): FetchColumn | undefined {
  return result.value?.columns.find((column) => column.name === columnId)
}

function presentCell(cell: Cell<GridFeatures, GridRow, unknown>): CellPresentation {
  const column = serverColumn(cell.column.id)
  const value = cell.getValue() as string | null
  return column === undefined
    ? { text: value ?? "null", align: "left", tone: "default" }
    : cellPresentation(value, column.type)
}

function openCell(cell: Cell<GridFeatures, GridRow, unknown>, event: MouseEvent) {
  const column = serverColumn(cell.column.id)
  const value = cell.getValue() as string | null
  if (
    event.shiftKey === false &&
    column !== undefined &&
    value !== null &&
    shouldOpenViewer(value, column.type)
  ) {
    viewer.value = { columnName: column.name, typeSql: column.type.sql, value }
    return
  }
  const rowIndex = Number(cell.row.id) - offset.value
  const rowHandle = result.value?.row_handles?.[rowIndex]
  if (column?.editable === true && typeof rowHandle === "string") {
    editError.value = ""
    editor.value = { column, value, rowHandle }
    return
  }
  if (column === undefined || value === null || !shouldOpenViewer(value, column.type)) return
  viewer.value = { columnName: column.name, typeSql: column.type.sql, value }
}

function cellTitle(cell: Cell<GridFeatures, GridRow, unknown>): string | undefined {
  const column = serverColumn(cell.column.id)
  if (column?.editable !== true) return result.value?.update_reason ?? undefined
  const value = cell.getValue() as string | null
  return shouldOpenViewer(value, column.type)
    ? "Double-click to view; Shift+double-click to edit"
    : "Double-click to edit"
}

async function saveCell(value: string | null) {
  const active = editor.value
  if (active === null) return
  editError.value = ""
  try {
    await updateCell.mutateAsync({
      node_id: props.nodeId,
      row_handle: active.rowHandle,
      column: active.column.name,
      value,
    })
    editor.value = null
    toast.success("Cell updated")
  } catch (error) {
    editError.value = messageOf(error, "Could not update the cell")
  }
}

function openInsert() {
  insertError.value = ""
  insertOpen.value = true
}

async function saveInsert(values: { column: string; value: string | null }[]) {
  insertError.value = ""
  try {
    await insertRow.mutateAsync({ node_id: props.nodeId, values })
    insertOpen.value = false
    toast.success("Row inserted")
  } catch (error) {
    insertError.value = messageOf(error, "Could not insert the row")
  }
}

async function deleteSelection() {
  const handles = selectedRowHandles.value
  if (!canDelete.value || handles.length === 0) return
  const accepted = await confirm({
    title: `Delete ${handles.length} ${handles.length === 1 ? "row" : "rows"}?`,
    message: "This cannot be undone.",
    confirmLabel: "Delete",
    danger: true,
  })
  if (!accepted) return
  try {
    await deleteRows.mutateAsync({ node_id: props.nodeId, row_handles: handles })
    table.resetCellSelection(true)
    toast.success(`${handles.length} ${handles.length === 1 ? "row" : "rows"} deleted`)
  } catch (error) {
    toast.error(messageOf(error, "Could not delete the selected rows"))
  }
}

function retry() {
  void rowsQuery.refetch()
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
      :can-copy="canCopy"
      :can-insert="canInsert"
      :insert-reason="result?.insert_reason ?? undefined"
      :can-delete="canDelete"
      :delete-reason="deleteReason"
      :delete-count="selectedRowHandles.length"
      @update:page-size="changePageSize"
      @update:filters="changeFilters"
      @update:sort="changeSort"
      @update:layout="changeLayout"
      @copy="copySelection"
      @insert="openInsert"
      @delete="deleteSelection"
    />

    <AppBanner
      v-if="rowsQuery.isError.value"
      tone="error"
      class="data-grid__state"
      data-testid="grid-error"
    >
      <div class="data-grid__error">
        <span>{{ messageOf(rowsQuery.error.value, "Could not read the rows") }}</span>
        <AppButton
          variant="secondary"
          label="Retry"
          size="sm"
          data-testid="grid-retry"
          @click="retry"
        />
      </div>
    </AppBanner>

    <div
      v-else
      ref="gridFocus"
      class="data-grid__scroll"
      role="grid"
      tabindex="0"
      data-testid="grid-focus"
      @keydown="handleGridKey"
    >
      <div
        v-if="rowsQuery.isPending.value"
        class="data-grid__skeleton"
        data-testid="grid-skeleton"
        aria-label="Loading rows"
      >
        <div
          v-for="index in 8"
          :key="index"
          class="data-grid__skeleton-row"
        />
      </div>
      <table
        v-else
        class="data-grid__table"
      >
        <thead>
          <tr
            v-for="headerGroup in table.getHeaderGroups()"
            :key="headerGroup.id"
          >
            <th
              class="data-grid__selector"
              scope="col"
            >
              <AppIconButton
                icon="select_all"
                tooltip="Select page"
                data-testid="grid-select-page"
                @click="selectPage"
              />
            </th>
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
                @click.stop="selectColumn(header.column.id)"
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
            <td class="data-grid__selector">
              <button
                type="button"
                class="data-grid__row-selector"
                :data-testid="`grid-select-row-${row.id}`"
                :aria-label="`Select row ${Number(row.id) + 1}`"
                @click="selectRow(row.id)"
              >
                {{ Number(row.id) + 1 }}
              </button>
            </td>
            <td
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-testid="`grid-cell-${row.id}-${cell.column.id}`"
              :class="{
                'data-grid__pinned': cell.column.getIsPinned() === 'start',
                'data-grid__selected': cell.getIsSelected(),
                'data-grid__editable': serverColumn(cell.column.id)?.editable === true,
              }"
              :title="cellTitle(cell)"
              :style="columnStyle(cell.column)"
              @mousedown="startSelection(cell, $event)"
              @mouseenter="cell.getSelectionExtendHandler()($event)"
              @dblclick="openCell(cell, $event)"
            >
              <span
                :class="{
                  'data-grid__align-right': presentCell(cell).align === 'right',
                  'data-grid__align-center': presentCell(cell).align === 'center',
                  'data-grid__null': presentCell(cell).tone === 'null',
                  'data-grid__monospace': presentCell(cell).monospace === true,
                }"
              >{{ presentCell(cell).text }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <AppEmptyState
        v-if="result !== undefined && rows.length === 0"
        class="data-grid__state"
        text="No rows"
        data-testid="grid-empty"
      />
      <div
        v-if="rowsQuery.isFetching.value && result !== undefined"
        class="data-grid__loading-overlay"
        data-testid="grid-loading-overlay"
        aria-label="Refreshing rows"
      />
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

    <CellValueDialog
      v-if="viewer !== null"
      :model-value="true"
      :column-name="viewer.columnName"
      :type-sql="viewer.typeSql"
      :value="viewer.value"
      @update:model-value="viewer = null"
    />
    <CellEditorDialog
      v-if="editor !== null"
      :model-value="true"
      :column="editor.column"
      :value="editor.value"
      :saving="updateCell.isPending.value"
      :error="editError"
      @save="saveCell"
      @update:model-value="editor = null"
    />
    <RowInsertDialog
      v-if="insertOpen"
      :model-value="true"
      :columns="result?.columns ?? []"
      :saving="insertRow.isPending.value"
      :error="insertError"
      @save="saveInsert"
      @update:model-value="insertOpen = false"
    />
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
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
  outline: none;
}

.data-grid__state {
  margin: 12px;
}

.data-grid__error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.data-grid__skeleton {
  display: grid;
  gap: 1px;
  padding: 1px;
}

.data-grid__skeleton-row {
  height: 34px;
  background: var(--dp-surface-raised);
  opacity: 0.65;
}

.data-grid__loading-overlay {
  position: absolute;
  z-index: var(--dp-layer-sticky);
  inset: 0;
  background: var(--dp-surface-raised);
  opacity: 0.3;
  pointer-events: none;
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
  background: var(--dp-surface);
  color: var(--dp-text-strong);
}

.data-grid__sortable {
  cursor: pointer;
}

.data-grid__pinned {
  position: sticky !important;
  z-index: var(--dp-layer-sticky);
  background: var(--dp-surface);
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

.data-grid__selector {
  width: 48px;
  min-width: 48px !important;
  max-width: 48px !important;
  text-align: center !important;
  background: var(--dp-surface);
}

.data-grid__row-selector {
  width: 100%;
  padding: 4px;
  border: 0;
  background: transparent;
  color: var(--dp-text-muted);
  cursor: pointer;
}

.data-grid__selected {
  box-shadow: inset 0 0 0 2px var(--dp-focus-border);
}

.data-grid__editable {
  cursor: cell;
}

.data-grid__table td > span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}

.data-grid__align-right {
  text-align: right;
}

.data-grid__align-center {
  text-align: center;
}

.data-grid__null {
  color: var(--dp-text-muted);
  font-style: italic;
}

.data-grid__monospace {
  font-family: monospace;
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
