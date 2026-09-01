<script setup lang="ts">
import {
  cellSelectionFeature,
  columnOrderingFeature,
  columnPinningFeature,
  columnResizingFeature,
  columnSizingFeature,
  columnVisibilityFeature,
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
import { computed, ref, useTemplateRef, watch } from "vue"
import type { CSSProperties } from "vue"

import type { Sort } from "@/client"
import { copyText } from "@/shared/clipboard"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  useToast,
} from "@/shared/ui"

import CellValueDialog from "./CellValueDialog.vue"
import { toTsv } from "./clipboard"
import { autoFitWidth } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"
import GridHeader from "./GridHeader.vue"
import { cellPresentation, shouldOpenViewer } from "./model"
import { selectedWholeRowIndexes, selectionMatrix } from "./selection"
import type { VisibleGridColumn } from "./selection"
import { toggleMultiSort, toggleSingleSort } from "./sortModel"
import { columnOf } from "./tabular"
import type {
  TabularColumn,
  TabularEditRequest,
  TabularPasteRequest,
  TabularVisibleColumn,
} from "./tabular"
import type { CellPresentation } from "./model"
import type { Filter, GridRow, PageSize } from "./types"

const props = withDefaults(
  defineProps<{
    columns: TabularColumn[]
    rows: GridRow[]
    page: number
    pageSize: PageSize
    filters: Filter[]
    sort: Sort[]
    layout: ColumnLayoutState
    hasMore?: boolean
    loading?: boolean
    refreshing?: boolean
    error?: string
    emptyText?: string
    updateReason?: string
    editableRowIds?: string[]
    showReset?: boolean
  }>(),
  {
    hasMore: false,
    loading: false,
    refreshing: false,
    error: "",
    emptyText: "No rows",
    updateReason: "",
    editableRowIds: () => [],
    showReset: true,
  }
)
const emit = defineEmits<{
  "update:pageSize": [value: PageSize]
  "update:filters": [value: Filter[]]
  "update:sort": [value: Sort[]]
  "update:layout": [value: ColumnLayoutState]
  "turn-page": [delta: -1 | 1]
  retry: []
  reset: []
  paste: [request: TabularPasteRequest]
  edit: [request: TabularEditRequest]
  "visible-columns": [columns: TabularVisibleColumn[]]
}>()
defineSlots<{
  commands(props: {
    canCopy: boolean
    selectedRowIndexes: number[]
    visibleColumns: TabularVisibleColumn[]
    requestPaste: () => void
  }): unknown
  "before-grid"(): unknown
  "cell-overlay"(props: {
    row: GridRow
    column: TabularColumn
    value: string | null
    visibleColumns: VisibleGridColumn[]
  }): unknown
  "after-rows"(props: {
    visibleColumns: TabularVisibleColumn[]
    nextRowNumber: number
  }): unknown
  "after-grid"(): unknown
}>()

const toast = useToast()
const gridFocus = useTemplateRef<HTMLElement>("gridFocus")
const viewer = ref<{ columnName: string; typeSql: string; value: string } | null>(null)
const editableRows = computed(() => new Set(props.editableRowIds))
const features = tableFeatures({
  columnSizingFeature,
  columnResizingFeature,
  columnOrderingFeature,
  columnVisibilityFeature,
  columnPinningFeature,
  cellSelectionFeature,
})
type GridFeatures = typeof features

const tableColumns = computed<ColumnDef<GridFeatures, GridRow>[]>(() =>
  props.columns.map((column, index) => ({
    id: column.id,
    header: column.label,
    accessorFn: (row) => row.values[index],
    minSize: 72,
    maxSize: 480,
    size: 160,
  }))
)
const tableState = computed(() => ({
  columnOrder: props.layout.columnOrder,
  columnVisibility: props.layout.columnVisibility,
  columnSizing: props.layout.columnSizing,
  columnPinning: { start: props.layout.pinnedLeft, end: [] },
}))

const table = useTable<GridFeatures, GridRow>({
  features,
  columns: tableColumns,
  data: computed(() => props.rows),
  getRowId: (row) => row.id,
  state: tableState,
  columnResizeMode: "onEnd",
  onColumnOrderChange: (updater) =>
    changeLayout({
      ...props.layout,
      columnOrder: functionalUpdate(updater, props.layout.columnOrder),
    }),
  onColumnVisibilityChange: (updater) =>
    changeLayout({
      ...props.layout,
      columnVisibility: functionalUpdate(updater, props.layout.columnVisibility),
    }),
  onColumnSizingChange: (updater) =>
    changeLayout({
      ...props.layout,
      columnSizing: functionalUpdate(updater, props.layout.columnSizing),
    }),
  onColumnPinningChange: (updater: Updater<ColumnPinningState>) => {
    const next = functionalUpdate(updater, {
      start: props.layout.pinnedLeft,
      end: [],
    })
    changeLayout({ ...props.layout, pinnedLeft: next.start })
  },
})

const columnWidthVariables = computed<Record<string, string>>(() =>
  Object.fromEntries(
    table.getAllLeafColumns().map((column) => [columnVariable(column.id), `${column.getSize()}px`])
  )
)
const canCopy = computed(() => table.getSelectedCellCount() > 0)
const visibleColumns = computed<VisibleGridColumn[]>(() => {
  const ordered = [
    ...table.getStartVisibleLeafColumns(),
    ...table.getCenterVisibleLeafColumns(),
  ]
  return ordered.flatMap((column) => {
    const valueIndex = props.columns.findIndex((item) => item.id === column.id)
    return valueIndex < 0 ? [] : [{ id: column.id, valueIndex }]
  })
})
const visibleColumnsForSlot = computed<TabularVisibleColumn[]>(() =>
  visibleColumns.value.flatMap((visible) => {
    const source = columnOf(props.columns, visible.id)
    const tableColumn = table.getColumn(visible.id)
    return source === undefined || tableColumn === undefined
      ? []
      : [
          {
            ...visible,
            column: source,
            pinned: tableColumn.getIsPinned() === "start",
            style: columnStyle(tableColumn),
          },
        ]
  })
)
const selectedRowIndexes = computed(() =>
  selectedWholeRowIndexes(table.getCellSelectionBounds(), visibleColumns.value.length)
)
const offset = computed(() => props.page * props.pageSize)
const range = computed(() => {
  if (props.rows.length === 0) return "Rows 0"
  return `Rows ${offset.value + 1}–${offset.value + props.rows.length}`
})

function changeLayout(layout: ColumnLayoutState) {
  table.resetCellSelection(true)
  emit("update:layout", layout)
}

function sortColumn(columnId: string, event: MouseEvent) {
  if (columnOf(props.columns, columnId)?.sortable !== true) return
  emit(
    "update:sort",
    event.shiftKey
      ? toggleMultiSort(props.sort, columnId)
      : toggleSingleSort(props.sort, columnId)
  )
}

function sortIndex(columnId: string): number {
  return props.sort.findIndex((item) => item.column === columnId)
}

function sortIcon(columnId: string): string {
  const index = sortIndex(columnId)
  if (index < 0) return "unfold_more"
  return props.sort[index]?.descending === true ? "arrow_downward" : "arrow_upward"
}

function sortDirection(columnId: string): "none" | "asc" | "desc" {
  const index = sortIndex(columnId)
  if (index < 0) return "none"
  return props.sort[index]?.descending === true ? "desc" : "asc"
}

function columnIsSortable(columnId: string): boolean {
  return columnOf(props.columns, columnId)?.sortable === true
}

function pinTooltip(column: Column<GridFeatures, GridRow, unknown>): string {
  const label = columnOf(props.columns, column.id)?.label ?? column.id
  return `${column.getIsPinned() === "start" ? "Unpin" : "Pin"} ${label}`
}

function columnVariable(columnId: string): string {
  const index = props.columns.findIndex((column) => column.id === columnId)
  return `--grid-column-${Math.max(0, index)}`
}

function columnStyle(column: Column<GridFeatures, GridRow, unknown>): CSSProperties {
  return {
    width: `var(${columnVariable(column.id)})`,
    insetInlineStart:
      column.getIsPinned() === "start"
        ? `calc(72px + ${column.getStart("start")}px)`
        : undefined,
  }
}

function togglePin(column: Column<GridFeatures, GridRow, unknown>) {
  column.pin(column.getIsPinned() === "start" ? false : "start")
}

function hideColumn(column: Column<GridFeatures, GridRow, unknown>) {
  column.toggleVisibility(false)
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

function autoFit(columnId: string) {
  const index = props.columns.findIndex((column) => column.id === columnId)
  const source = props.columns[index]
  if (index < 0 || source === undefined) return
  const values = props.rows.map((row) => row.values[index] ?? null)
  const width = autoFitWidth(source.label, values, measureFullText, { min: 72, max: 480 })
  changeLayout({
    ...props.layout,
    columnSizing: { ...props.layout.columnSizing, [columnId]: width },
  })
}

function startSelection(cell: Cell<GridFeatures, GridRow, unknown>, event: MouseEvent) {
  gridFocus.value?.focus()
  cell.getSelectionStartHandler()(event)
}

function selectRow(rowId: string) {
  const first = visibleColumns.value[0]
  const last = visibleColumns.value.at(-1)
  if (first === undefined || last === undefined) return
  table.selectCellRange({
    anchorRowId: rowId,
    focusRowId: rowId,
    anchorColumnId: first.id,
    focusColumnId: last.id,
  })
}

function selectColumn(columnId: string) {
  const first = props.rows[0]
  const last = props.rows.at(-1)
  if (first === undefined || last === undefined) return
  table.selectCellRange({
    anchorRowId: first.id,
    focusRowId: last.id,
    anchorColumnId: columnId,
    focusColumnId: columnId,
  })
}

function selectPage() {
  const firstRow = props.rows[0]
  const lastRow = props.rows.at(-1)
  const firstColumn = visibleColumns.value[0]
  const lastColumn = visibleColumns.value.at(-1)
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
  const matrix = selectionMatrix(
    props.rows,
    visibleColumns.value,
    table.getCellSelectionBounds()
  )
  if (matrix.length === 0) return
  try {
    await copyText(toTsv(matrix))
  } catch {
    toast.error("Could not copy the selection")
  }
}

function requestPaste() {
  const bounds = table.getCellSelectionBounds()[0]
  if (bounds === undefined) return
  emit("paste", { bounds, columns: [...visibleColumns.value] })
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
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") {
    event.preventDefault()
    requestPaste()
  }
}

function presentCell(cell: Cell<GridFeatures, GridRow, unknown>): CellPresentation {
  const column = columnOf(props.columns, cell.column.id)
  const value = cellValue(cell)
  return column === undefined
    ? { text: value ?? "null", align: "left", tone: "default" }
    : cellPresentation(value, column.type)
}

function cellValue(cell: Cell<GridFeatures, GridRow, unknown>): string | null {
  return cell.getValue() as string | null
}

function cellIsEditable(cell: Cell<GridFeatures, GridRow, unknown>): boolean {
  return (
    columnOf(props.columns, cell.column.id)?.editable === true &&
    editableRows.value.has(cell.row.id)
  )
}

function openCell(cell: Cell<GridFeatures, GridRow, unknown>, event: MouseEvent) {
  const column = columnOf(props.columns, cell.column.id)
  if (column === undefined) return
  const value = cell.getValue() as string | null
  const opensViewer = shouldOpenViewer(value, column.type)
  if (event.shiftKey === false && value !== null && opensViewer) {
    viewer.value = { columnName: column.label, typeSql: column.type.sql, value }
    return
  }
  if (cellIsEditable(cell)) {
    emit("edit", {
      row: cell.row.original,
      rowIndex: cell.row.index,
      column,
      value,
    })
    return
  }
  if (value === null || !opensViewer) return
  viewer.value = { columnName: column.label, typeSql: column.type.sql, value }
}

function cellTitle(cell: Cell<GridFeatures, GridRow, unknown>): string | undefined {
  const column = columnOf(props.columns, cell.column.id)
  if (column === undefined) return undefined
  if (!cellIsEditable(cell)) return props.updateReason || undefined
  const value = cell.getValue() as string | null
  return shouldOpenViewer(value, column.type)
    ? "Double-click to view; Shift+double-click to edit"
    : "Double-click to edit"
}

function rowNumber(row: GridRow, index: number): number {
  const fromId = Number(row.id)
  return Number.isFinite(fromId) ? fromId + 1 : offset.value + index + 1
}

watch(
  visibleColumnsForSlot,
  (columns) => emit("visible-columns", columns.map((column) => ({ ...column }))),
  { immediate: true }
)
watch(
  () => [props.rows, props.columns] as const,
  () => table.resetCellSelection(true)
)

defineExpose({
  clearSelection: () => table.resetCellSelection(true),
  focus: (selector: string) =>
    gridFocus.value?.querySelector<HTMLElement>(selector)?.focus(),
})
</script>

<template>
  <div
    class="data-grid"
    data-testid="row-grid"
    :style="columnWidthVariables"
  >
    <GridHeader
      :page-size="pageSize"
      :columns="columns"
      :filters="filters"
      :sort="sort"
      :layout="layout"
      :can-copy="canCopy"
      @update:page-size="emit('update:pageSize', $event)"
      @update:filters="emit('update:filters', $event)"
      @update:sort="emit('update:sort', $event)"
      @update:layout="changeLayout"
      @copy="copySelection"
    >
      <template #commands>
        <slot
          name="commands"
          :can-copy="canCopy"
          :selected-row-indexes="selectedRowIndexes"
          :visible-columns="visibleColumnsForSlot"
          :request-paste="requestPaste"
        />
      </template>
    </GridHeader>

    <AppBanner
      v-if="error"
      tone="error"
      class="data-grid__state"
      data-testid="grid-error"
    >
      <div class="data-grid__error">
        <span>{{ error }}</span>
        <div class="data-grid__error-actions">
          <AppButton
            v-if="showReset"
            variant="secondary"
            label="Reset query"
            size="sm"
            data-testid="grid-reset-query"
            @click="emit('reset')"
          />
          <AppButton
            variant="secondary"
            label="Retry"
            size="sm"
            data-testid="grid-retry"
            @click="emit('retry')"
          />
        </div>
      </div>
    </AppBanner>

    <slot name="before-grid" />

    <div
      v-if="!error"
      ref="gridFocus"
      class="data-grid__scroll"
      role="grid"
      tabindex="0"
      data-testid="grid-focus"
      @keydown="handleGridKey"
    >
      <div
        v-if="loading"
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
                'data-grid__sortable': columnIsSortable(header.column.id),
                'data-grid__pinned': header.column.getIsPinned() === 'start',
              }"
              :style="columnStyle(header.column)"
            >
              <button
                type="button"
                class="data-grid__column-name"
                :aria-label="`Select column ${columnOf(columns, header.column.id)?.label ?? header.column.id}`"
                :data-testid="`grid-column-select-${header.column.id}`"
                @click="selectColumn(header.column.id)"
              >
                {{ columnOf(columns, header.column.id)?.label ?? header.column.id }}
              </button>
              <span class="data-grid__column-actions">
                <span
                  v-if="sortIndex(header.column.id) >= 0"
                  :data-testid="`grid-sort-priority-${header.column.id}`"
                  class="data-grid__sort-priority"
                >{{ sortIndex(header.column.id) + 1 }}</span>
                <AppIconButton
                  v-if="columnIsSortable(header.column.id)"
                  :icon="sortIcon(header.column.id)"
                  :tooltip="`Sort by ${columnOf(columns, header.column.id)?.label ?? header.column.id}`"
                  :data-direction="sortDirection(header.column.id)"
                  :data-testid="`grid-sort-direction-${header.column.id}`"
                  @click.stop="sortColumn(header.column.id, $event)"
                />
                <AppIconButton
                  icon="push_pin"
                  :class="{
                    'data-grid__pin--active': header.column.getIsPinned() === 'start',
                  }"
                  :aria-pressed="header.column.getIsPinned() === 'start'"
                  :tooltip="pinTooltip(header.column)"
                  :data-testid="`grid-pin-${header.column.id}`"
                  @click.stop="togglePin(header.column)"
                />
                <AppIconButton
                  icon="visibility_off"
                  :tooltip="`Hide ${columnOf(columns, header.column.id)?.label ?? header.column.id}`"
                  :data-testid="`grid-hide-${header.column.id}`"
                  @click.stop="hideColumn(header.column)"
                />
              </span>
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
            v-for="(row, rowIndex) in table.getRowModel().rows"
            :key="row.id"
            :data-testid="`grid-row-${row.id}`"
          >
            <td class="data-grid__selector">
              <button
                type="button"
                class="data-grid__row-selector"
                :data-testid="`grid-select-row-${row.id}`"
                :aria-label="`Select row ${rowNumber(row.original, rowIndex)}`"
                @click="selectRow(row.id)"
              >
                {{ rowNumber(row.original, rowIndex) }}
              </button>
            </td>
            <td
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-testid="`grid-cell-${row.id}-${cell.column.id}`"
              :class="{
                'data-grid__pinned': cell.column.getIsPinned() === 'start',
                'data-grid__selected': cell.getIsSelected(),
                'data-grid__editable': cellIsEditable(cell),
              }"
              :title="cellTitle(cell)"
              :style="columnStyle(cell.column)"
              @mousedown="startSelection(cell, $event)"
              @mouseenter="cell.getSelectionExtendHandler()($event)"
              @dblclick="openCell(cell, $event)"
            >
              <span
                :class="{
                  'data-grid__null': presentCell(cell).tone === 'null',
                  'data-grid__monospace': presentCell(cell).monospace === true,
                }"
              >{{ presentCell(cell).text }}</span>
              <slot
                name="cell-overlay"
                :row="row.original"
                :column="columnOf(columns, cell.column.id)!"
                :value="cellValue(cell)"
                :visible-columns="visibleColumns"
              />
            </td>
          </tr>
          <slot
            name="after-rows"
            :visible-columns="visibleColumnsForSlot"
            :next-row-number="offset + rows.length + 1"
          />
        </tbody>
      </table>
      <AppEmptyState
        v-if="!loading && rows.length === 0 && emptyText"
        class="data-grid__state"
        :text="emptyText"
        data-testid="grid-empty"
      />
      <div
        v-if="refreshing && !loading"
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
        :disable="page === 0"
        data-testid="grid-prev"
        @click="emit('turn-page', -1)"
      />
      <AppIconButton
        icon="chevron_right"
        tooltip="Next page"
        :disable="!hasMore"
        data-testid="grid-next"
        @click="emit('turn-page', 1)"
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

    <slot name="after-grid" />
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

.data-grid__error-actions {
  display: flex;
  gap: 8px;
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

.data-grid__table th:not(.data-grid__selector) {
  padding-inline-end: 80px;
}

.data-grid__sortable {
  padding-inline-end: 112px !important;
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
  inset-inline-end: 0;
  width: 6px;
  cursor: col-resize;
  touch-action: none;
  user-select: none;
}

.data-grid__resize:hover {
  background: var(--dp-separator-active);
}

.data-grid__selector {
  width: 72px;
  min-width: 72px !important;
  max-width: 72px !important;
  text-align: center !important;
  background: var(--dp-surface);
  position: sticky !important;
  inset-inline-start: 0;
  z-index: var(--dp-layer-sticky);
  border-left: 1px solid var(--dp-border-faint);
}

.data-grid__table thead .data-grid__selector {
  z-index: var(--dp-layer-overlay);
}

.data-grid__column-name {
  max-width: 100%;
  padding: 0;
  border: 0;
  overflow: hidden;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: inherit;
  text-overflow: ellipsis;
  cursor: pointer;
}

.data-grid__column-actions {
  position: absolute;
  inset-block-start: 0;
  inset-inline-end: 4px;
  display: flex;
  align-items: center;
}

.data-grid__pin--active {
  color: var(--dp-link);
}

.data-grid__sort-priority {
  min-width: 12px;
  color: var(--dp-text-muted);
  font-size: 10px;
  text-align: center;
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
