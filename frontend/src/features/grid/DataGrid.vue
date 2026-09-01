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
import { computed, nextTick, ref, toRef, useTemplateRef, watch } from "vue"
import type { CSSProperties } from "vue"

import type {
  FetchColumn,
  FetchReference,
  FetchRequest,
  ReferencedRows,
  RowsView,
  Sort,
} from "@/client"
import { messageOf, statusOf } from "@/shared/api/errors"
import { copyText, readText } from "@/shared/clipboard"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  useConfirm,
  useToast,
} from "@/shared/ui"

import {
  useCreateRelationFromSource,
  useDeleteRows,
  useDownloadPage,
  useExportRows,
  useImportRows,
  useFollowReference,
  useForgetRowsPage,
  useInsertRow,
  useRowsPage,
  useUpdateCell,
  useUpdateCells,
} from "./api"
import CellEditorDialog from "./CellEditorDialog.vue"
import CellValueDialog from "./CellValueDialog.vue"
import CreateTableDialog from "./CreateTableDialog.vue"
import { fromTsv, toTsv } from "./clipboard"
import { autoFitWidth, defaultColumnLayout } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"
import {
  filenameFromDisposition,
  saveBrowserDownload,
  saveNativeDownload,
} from "./download"
import type { DownloadScope } from "./download"
import DownloadDialog from "./DownloadDialog.vue"
import ShareDialog from "@/features/shares/ShareDialog.vue"
import {
  droppedByReconciliation,
  pageSizeOf,
  storedFromView,
  viewOfGrid,
} from "@/features/shares/sharedView"
import GridHeader from "./GridHeader.vue"
import ImportDialog from "./ImportDialog.vue"
import RowInsertRow from "./RowInsertRow.vue"
import type { InsertGridColumn } from "./RowInsertRow.vue"
import { cellPresentation, shouldOpenViewer, toGridRows } from "./model"
import { keyValues, referencesLedBy } from "./references"
import type { CellPresentation } from "./model"
import {
  loadGridState,
  loadPageSize,
  reconcileGridState,
  saveGridState,
  savePageSize,
} from "./persist"
import {
  buildFetchRequest,
  prunedToColumns,
  withFilters,
  withPage,
  withPageSize,
} from "./queryState"
import { withSort } from "./queryState"
import { toggleMultiSort, toggleSingleSort } from "./sortModel"
import { planPaste, planRowPaste } from "./paste"
import type { PasteColumn } from "./paste"
import { selectedWholeRowIndexes, selectionMatrix } from "./selection"
import type { VisibleGridColumn } from "./selection"
import type { Filter, GridQueryState, GridRow, PageSize, StoredGridState } from "./types"

const props = defineProps<{
  connectorId: string
  nodeId: string
  title?: string
  canDescribe?: boolean
  /** The source's wording for one non-tabular view of these rows. */
  contentTitle?: string
  /**
   * A predicate the source built for a reference somebody followed here.
   *
   * A prop rather than a call into the grid: the panel may have been created
   * a moment ago and not be mounted yet, which a call does not survive. A new
   * array each time, so following the same key twice applies twice.
   */
  referenceFilters?: Filter[] | null
  /**
   * The view a link asked this tab to show, once.
   *
   * A prop for the same reason `referenceFilters` is one: the panel may have
   * been opened a moment ago, or have been open already, and neither survives
   * a call. See D60.
   */
  sharedView?: RowsView | null
}>()
const emit = defineEmits<{
  describe: []
  content: []
  chart: [request: FetchRequest, columns: string[]]
  follow: [target: ReferencedRows]
}>()
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
const persistedQueryState = ref<GridQueryState>({ ...queryState.value })
const queryAwaitingPersistence = ref<GridQueryState | null>(null)
const request = computed(() => buildFetchRequest(props.nodeId, queryState.value))
const refreshNext = ref(false)
/** One explicit reload is spent by one fetch: whichever asks for it first. */
function takeRefresh() {
  const wanted = refreshNext.value
  refreshNext.value = false
  return wanted
}
const rowsQuery = useRowsPage(toRef(props, "connectorId"), request, takeRefresh)

async function refreshRows() {
  refreshNext.value = true
  try {
    await rowsQuery.refetch()
  } finally {
    refreshNext.value = false
  }
}
const result = computed(() => rowsQuery.data.value)
const rows = computed(() =>
  result.value === undefined || rowsQuery.isError.value
    ? []
    : toGridRows(result.value, request.value.offset ?? 0)
)
const layout = ref<ColumnLayoutState>({ ...EMPTY_LAYOUT })
const viewer = ref<{ columnName: string; typeSql: string; value: string } | null>(null)
const editor = ref<{
  column: FetchColumn
  value: string | null
  rowHandle: string
} | null>(null)
const editError = ref("")
const insertOpen = ref(false)
const importOpen = ref(false)
const createTableOpen = ref(false)
const downloadOpen = ref(false)
const shareOpen = ref(false)
/** What this tab is showing, in the shape a link carries. */
const sharedViewOfThisGrid = computed(() => viewOfGrid(queryState.value, layout.value))
const importError = ref("")
const createTableError = ref("")
const insertError = ref("")
const updateCell = useUpdateCell(toRef(props, "connectorId"))
const updateCells = useUpdateCells(toRef(props, "connectorId"))
const insertRow = useInsertRow(toRef(props, "connectorId"))
const deleteRows = useDeleteRows(toRef(props, "connectorId"))
const downloadPage = useDownloadPage(toRef(props, "connectorId"))
const exportRows = useExportRows(toRef(props, "connectorId"))
const importRows = useImportRows(toRef(props, "connectorId"))
const createRelation = useCreateRelationFromSource()
const followReference = useFollowReference(toRef(props, "connectorId"))
const forgetRowsPage = useForgetRowsPage(toRef(props, "connectorId"))
const gridFocus = useTemplateRef<HTMLElement>("gridFocus")
const insertForm = useTemplateRef<{
  fill: (values: { column: string; value: string | null }[]) => void
}>("insertForm")
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
const canPaste = computed(
  () => canCopy.value && result.value?.update_supported === true
)
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
const insertGridColumns = computed<InsertGridColumn[]>(() =>
  [...table.getStartVisibleLeafColumns(), ...table.getCenterVisibleLeafColumns()].flatMap(
    (column) => {
      const source = serverColumn(column.id)
      return source === undefined
        ? []
        : [{ column: source, pinned: column.getIsPinned() === "start", style: columnStyle(column) }]
    }
  )
)
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
  queryAwaitingPersistence.value = next
  queryState.value = next
}

function changeSort(sort: Sort[]) {
  const next = withSort(queryState.value, sort)
  queryAwaitingPersistence.value = next
  queryState.value = next
}

function changeLayout(next: ColumnLayoutState) {
  table.resetCellSelection(true)
  layout.value = next
  saveGridState(props.connectorId, props.nodeId, {
    ...next,
    filters: persistedQueryState.value.filters,
    sort: persistedQueryState.value.sort,
  })
}

function saveQueryState(state: GridQueryState) {
  const serverColumns = result.value?.columns
  const stored = loadGridState(props.connectorId, props.nodeId)
  const base: StoredGridState =
    stored === null
      ? { ...defaultColumnLayout(serverColumns ?? []), filters: [], sort: [] }
      : serverColumns === undefined
        ? stored
        : reconcileGridState(stored, serverColumns)
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

function sortIcon(columnName: string): string {
  const index = sortIndex(columnName)
  if (index < 0) return "unfold_more"
  return queryState.value.sort[index]?.descending === true
    ? "arrow_downward"
    : "arrow_upward"
}

function sortDirection(columnName: string): "none" | "asc" | "desc" {
  const index = sortIndex(columnName)
  if (index < 0) return "none"
  return queryState.value.sort[index]?.descending === true ? "desc" : "asc"
}

function columnIsSortable(columnName: string): boolean {
  return (
    result.value?.columns.find((column) => column.name === columnName)?.sortable === true
  )
}

function pinTooltip(column: Column<GridFeatures, GridRow, unknown>): string {
  return `${column.getIsPinned() === "start" ? "Unpin" : "Pin"} ${column.id}`
}

function columnVariable(columnName: string): string {
  const index = result.value?.columns.findIndex((column) => column.name === columnName) ?? -1
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

const pasteColumns = computed<PasteColumn[]>(() =>
  visibleGridColumns.value.map((column) => ({
    name: column.id,
    valueIndex: column.valueIndex,
    editable: serverColumn(column.id)?.editable === true,
  }))
)

/**
 * Put a copied block back, from the top-left of the selection.
 *
 * Everything that can be known here is checked here — where the block lands,
 * whether it fits, whether those columns may be edited — and everything that
 * cannot is the source's answer: whether the rows still hold their version,
 * and whether each value can be read as its column's type.
 */
async function pasteSelection() {
  const bounds = table.getCellSelectionBounds()[0]
  if (bounds === undefined) return
  let text = ""
  try {
    text = await readText()
  } catch {
    toast.error("Could not read the clipboard")
    return
  }
  const block = fromTsv(text)
  if (block === null) {
    toast.info("The clipboard does not hold a rectangle of cells")
    return
  }
  const plan = planPaste(
    block,
    rows.value,
    result.value?.row_handles ?? [],
    pasteColumns.value,
    { rowIndex: bounds.minRowIndex, columnIndex: bounds.minColumnIndex }
  )
  if (!plan.ok) {
    toast.info(plan.reason)
    return
  }
  try {
    const answer = await updateCells.mutateAsync({
      node_id: props.nodeId,
      rows: plan.rows,
    })
    // Not a failure: the source read the values, wrote nothing, and said
    // which of them its columns cannot take.
    if (answer.kind === "rejected") {
      const first = answer.cells[0]
      const where = first === undefined ? "" : ` (${first.column})`
      toast.error(
        `${answer.cells.length} pasted ${answer.cells.length === 1 ? "value" : "values"} ` +
          `cannot be read by ${answer.cells.length === 1 ? "its" : "their"} column${where}`
      )
      return
    }
    toast.success(
      `${answer.rows.length} ${answer.rows.length === 1 ? "row" : "rows"} updated`
    )
  } catch (error) {
    toast.error(messageOf(error, "Could not paste those cells"))
  }
}

/**
 * Fill the row being inserted from a copied one.
 *
 * The same clipboard and the same TSV as everywhere else; what differs is
 * where it lands, and that a row the source numbers or generates for itself
 * cannot be dictated — those values are named as left out rather than
 * silently dropped.
 */
const importColumns = computed(() =>
  (result.value?.columns ?? []).filter((column) => column.insertable === true)
)

function openImport() {
  importError.value = ""
  importOpen.value = true
}

async function bringIn(value: {
  connectorId: string
  nodeId: string
  columns: { source: string; target: string }[]
}) {
  importError.value = ""
  try {
    const answer = await importRows.mutateAsync({
      node_id: props.nodeId,
      source_connector_id: value.connectorId,
      source_node_id: value.nodeId,
      columns: value.columns,
    })
    importOpen.value = false
    toast.success(
      answer.truncated
        ? `${answer.inserted} rows brought in; the source held more`
        : `${answer.inserted} rows brought in`
    )
  } catch (error) {
    importError.value = messageOf(error, "Could not bring those rows in")
  }
}

function openCreateTable() {
  createTableError.value = ""
  createTableOpen.value = true
}

async function createTable(value: {
  connectorId: string
  parentNodeId: string
  name: string
  columns: { source: string; target: string; type_code: string }[]
}) {
  createTableError.value = ""
  try {
    const answer = await createRelation.mutateAsync({
      connectorId: value.connectorId,
      body: {
        parent_node_id: value.parentNodeId,
        name: value.name,
        source_connector_id: props.connectorId,
        source_node_id: props.nodeId,
        columns: value.columns,
      },
    })
    createTableOpen.value = false
    toast.success(`Created ${answer.node.name} with ${answer.inserted} rows`)
  } catch (error) {
    createTableError.value = messageOf(error, "Could not create that table")
  }
}

async function pasteIntoInsert() {
  let text = ""
  try {
    text = await readText()
  } catch {
    toast.error("Could not read the clipboard")
    return
  }
  const block = fromTsv(text)
  if (block === null) {
    toast.info("The clipboard does not hold a row of cells")
    return
  }
  const plan = planRowPaste(
    block,
    insertGridColumns.value.map((entry) => ({
      name: entry.column.name,
      insertable: entry.column.insertable === true,
    }))
  )
  if (!plan.ok) {
    toast.info(plan.reason)
    return
  }
  insertForm.value?.fill(plan.fill.values)
  if (plan.fill.skipped.length > 0) {
    toast.info(`Left to the source: ${plan.fill.skipped.join(", ")}`)
  }
}

async function copySelection() {
  const matrix = selectionMatrix(rows.value, visibleGridColumns.value, table.getCellSelectionBounds())
  if (matrix.length === 0) return
  try {
    await copyText(toTsv(matrix))
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
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") {
    event.preventDefault()
    void pasteSelection()
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

async function runDownload(scope: DownloadScope) {
  if (result.value === undefined || visibleGridColumns.value.length === 0) return
  const fallback = `${props.title ?? "table"}.csv`
  try {
    if (scope === "all") {
      const exported = await exportRows.mutateAsync({
        node_id: props.nodeId,
        title: props.title ?? "table",
        columns: visibleGridColumns.value.map((column) => column.id),
        filters: [...queryState.value.filters],
        sort: [...queryState.value.sort],
      })
      saveNativeDownload(exported.download_url)
      downloadOpen.value = false
      toast.success(
        `${exported.row_count} rows exported and saved to your Downloads folder`
      )
      return
    }
    const downloaded = await downloadPage.mutateAsync({
      ...request.value,
      title: props.title ?? "table",
      columns: visibleGridColumns.value.map((column) => column.id),
    })
    saveBrowserDownload(
      downloaded.blob,
      filenameFromDisposition(downloaded.disposition, fallback)
    )
    downloadOpen.value = false
    toast.success("Page downloaded and saved to your Downloads folder")
  } catch (error) {
    toast.error(messageOf(error, "Could not create this download"))
  }
}

function openChart(): void {
  if (result.value === undefined || visibleGridColumns.value.length === 0) return
  emit(
    "chart",
    { ...request.value, filters: [...queryState.value.filters], sort: [...queryState.value.sort] },
    visibleGridColumns.value.map((column) => column.id)
  )
}

const NO_REFERENCES: FetchReference[] = []
// Worked out once per answer rather than once per cell: the template asks
// about every cell of every row on every render, and a page runs to five
// hundred rows.
const referencesByColumn = computed(() => {
  const visible = visibleGridColumns.value.map((column) => column.id)
  const references = result.value?.references ?? []
  const led = new Map<string, FetchReference[]>()
  for (const id of visible) {
    const found = referencesLedBy(references, id, visible)
    if (found.length > 0) led.set(id, found)
  }
  return led
})

/**
 * The ways out drawn in this cell, for this row.
 *
 * A cell with nothing in it draws none: an empty cell has no value to act on,
 * which is the same reason a null one does not open the viewer. Whether an
 * incomplete key names a row is not decided here — the source answers that
 * when the arrow is actually pressed.
 */
function cellReferences(cell: Cell<GridFeatures, GridRow, unknown>): FetchReference[] {
  if ((cell.getValue() as string | null) === null) return NO_REFERENCES
  return referencesByColumn.value.get(cell.column.id) ?? NO_REFERENCES
}

async function follow(row: GridRow, reference: FetchReference) {
  const columns = result.value?.columns
  if (columns === undefined) return
  const values = keyValues(reference, columns, row.values)
  if (values === null) {
    toast.info("This page was read before the relation changed; reload it")
    return
  }
  try {
    const target = await followReference.mutateAsync({
      node_id: props.nodeId,
      reference: reference.name,
      values,
    })
    // The source answered that the key names nothing. Not a failure: an empty
    // key is a fact about the row, and it says so in the source's own words.
    if (target.kind === "none") {
      toast.info(target.reason)
      return
    }
    emit("follow", target)
  } catch (error) {
    toast.error(messageOf(error, "Could not follow this reference"))
  }
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

async function openInsert() {
  insertError.value = ""
  const visibility = { ...layout.value.columnVisibility }
  for (const column of result.value?.columns ?? []) {
    if (column.insert_required === true) visibility[column.name] = true
  }
  if (Object.keys(visibility).length > 0) {
    changeLayout({ ...layout.value, columnVisibility: visibility })
  }
  insertOpen.value = true
  await nextTick()
  gridFocus.value
    ?.querySelector<HTMLInputElement>('[data-testid^="grid-insert-value-"]')
    ?.focus()
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

function cancelInsert() {
  insertOpen.value = false
  insertError.value = ""
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

function resetQuery() {
  const next = {
    ...withPage(queryState.value, 0),
    filters: [],
    sort: [],
  }
  queryAwaitingPersistence.value = null
  persistedQueryState.value = next
  saveQueryState(next)
  queryState.value = next
}

/**
 * The query a 422 interrupted, held while the grid asks the source what
 * columns it has now.
 *
 * A filter and a sort name a column by name and both outlive a reload, so a
 * column renamed or dropped — here, in another tab, or by somebody else —
 * leaves a stored query the source refuses every time it is asked. Rather than
 * reading the refusal, the grid asks again without filters or sorting and
 * keeps back everything the fresh answer still knows about.
 */
const quarantinedQuery = ref<GridQueryState | null>(null)
let recoveredFrom = ""

watch(
  () => rowsQuery.isError.value,
  (failed) => {
    if (!failed || quarantinedQuery.value !== null) return
    if (statusOf(rowsQuery.error.value) !== 422) return
    const current = queryState.value
    if (current.filters.length === 0 && current.sort.length === 0) return
    // Once per exact query: a 422 that is not about a missing column would
    // otherwise be cleared, restored, refused and cleared again for ever.
    const stamp = JSON.stringify(request.value)
    if (recoveredFrom === stamp) return
    recoveredFrom = stamp
    const cleared = { ...current, page: 0, filters: [], sort: [] }
    // Clearing the query lands on a key the client may already hold an answer
    // for — the one read before the column changed, which still lists it.
    // Pruning against that decides nothing, so the answer is forgotten first.
    forgetRowsPage(buildFetchRequest(props.nodeId, cleared))
    quarantinedQuery.value = current
    queryState.value = cleared
  }
)

watch(
  () => result.value?.columns,
  (serverColumns) => {
    const quarantined = quarantinedQuery.value
    if (serverColumns === undefined || quarantined === null) return
    quarantinedQuery.value = null
    const { state, dropped } = prunedToColumns(quarantined, serverColumns)
    if (dropped.length > 0) {
      toast.info(
        `${dropped.join(", ")} ${dropped.length === 1 ? "is" : "are"} no longer in this relation, so the query no longer ${dropped.length === 1 ? "uses it" : "uses them"}`
      )
    }
    queryAwaitingPersistence.value = null
    persistedQueryState.value = state
    saveQueryState(state)
    queryState.value = state
  }
)

/**
 * Whether a followed reference decided this tab's query.
 *
 * The stored query of a relation is restored the first time the source names
 * its columns, which happens after the panel is opened — so without this the
 * remembered filters would land on top of the ones somebody just navigated
 * by. What was navigated to is stored in its turn, exactly as a filter the
 * user typed is: the tab keeps showing what it was last asked to show.
 */
let referenceApplied = false

watch(
  () => props.referenceFilters,
  (filters) => {
    if (filters === undefined || filters === null) return
    referenceApplied = true
    const next = withFilters(queryState.value, filters)
    queryAwaitingPersistence.value = null
    persistedQueryState.value = next
    saveQueryState(next)
    queryState.value = next
  },
  { immediate: true }
)

/**
 * The shared view this tab was opened by, applied once the source has named
 * its columns.
 *
 * Both halves of a link land here — the query and the column layout — and both
 * go through `reconcileGridState`, which is what a tab restored from storage
 * uses. So a column the relation no longer has is dropped by one function,
 * in one place, and what went is said rather than silently missing (D60).
 *
 * Waiting for the columns rather than applying at once: a filter naming a
 * column that has gone would otherwise be sent to the source and refused.
 */
let appliedShare: RowsView | null = null
let restoredKey = ""

watch(
  [() => props.sharedView, () => result.value?.columns] as const,
  ([view, serverColumns]) => {
    if (view === undefined || view === null || serverColumns === undefined) return
    if (appliedShare === view) return
    appliedShare = view
    // The stored query must not land on top of what the link asked for; the
    // restore below is keyed by the tab it has already run for.
    restoredKey = `${props.connectorId}\u0000${props.nodeId}`
    referenceApplied = true

    const wanted = storedFromView(view)
    const kept = reconcileGridState(wanted, serverColumns)
    changeLayout({
      columnOrder: kept.columnOrder,
      columnVisibility: kept.columnVisibility,
      columnSizing: kept.columnSizing,
      pinnedLeft: kept.pinnedLeft,
    })
    const next: GridQueryState = {
      page: 0,
      pageSize: pageSizeOf(view, queryState.value.pageSize),
      filters: kept.filters,
      sort: kept.sort,
    }
    queryAwaitingPersistence.value = null
    persistedQueryState.value = next
    saveQueryState(next)
    queryState.value = next

    const dropped = droppedByReconciliation(wanted, kept)
    if (dropped.length > 0) {
      toast.info(
        `${dropped.join(", ")} ${dropped.length === 1 ? "is" : "are"} no longer in this relation, so the shared query does not use ${dropped.length === 1 ? "it" : "them"}`
      )
    }
  },
  { immediate: true }
)

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
      persistedQueryState.value = { ...queryState.value }
      return
    }
    const reconciled = reconcileGridState(stored, serverColumns)
    layout.value = {
      columnOrder: reconciled.columnOrder,
      columnVisibility: reconciled.columnVisibility,
      columnSizing: reconciled.columnSizing,
      pinnedLeft: reconciled.pinnedLeft,
    }
    const restored = {
      ...queryState.value,
      page: 0,
      filters: referenceApplied ? queryState.value.filters : reconciled.filters,
      sort: referenceApplied ? queryState.value.sort : reconciled.sort,
    }
    persistedQueryState.value = restored
    queryState.value = restored
  },
  { immediate: true }
)

watch(
  () => [rowsQuery.isSuccess.value, rowsQuery.dataUpdatedAt.value] as const,
  ([isSuccess]) => {
    const pending = queryAwaitingPersistence.value
    if (!isSuccess || pending === null || queryState.value !== pending) return
    persistedQueryState.value = pending
    saveQueryState(pending)
    queryAwaitingPersistence.value = null
  }
)

watch(
  () => [props.connectorId, props.nodeId],
  () => {
    restoredKey = ""
    recoveredFrom = ""
    referenceApplied = false
    quarantinedQuery.value = null
    insertOpen.value = false
    insertError.value = ""
    importOpen.value = false
    importError.value = ""
    createTableOpen.value = false
    createTableError.value = ""
    layout.value = { ...EMPTY_LAYOUT }
    const reset = { ...withPage(queryState.value, 0), filters: [], sort: [] }
    queryAwaitingPersistence.value = null
    persistedQueryState.value = reset
    queryState.value = reset
  }
)

defineExpose({
  reload: async () => {
    await refreshRows()
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
      :can-copy="canCopy"
      :can-paste="canPaste"
      :paste-supported="result?.update_supported === true"
      :can-insert="canInsert"
      :can-import="canInsert && importColumns.length > 0"
      :insert-supported="result?.insert_supported === true"
      :can-delete="canDelete"
      :delete-supported="result?.delete_supported === true"
      :delete-count="selectedRowHandles.length"
      :can-download="result !== undefined && visibleGridColumns.length > 0"
      :can-share="result !== undefined"
      :downloading="downloadPage.isPending.value || exportRows.isPending.value"
      :can-describe="canDescribe"
      :content-title="contentTitle"
      :can-chart="result !== undefined && visibleGridColumns.length > 0"
      :can-create-table="result !== undefined && result.columns.length > 0"
      @update:page-size="changePageSize"
      @update:filters="changeFilters"
      @update:sort="changeSort"
      @update:layout="changeLayout"
      @copy="copySelection"
      @paste="pasteSelection"
      @insert="openInsert"
      @bring-in="openImport"
      @delete="deleteSelection"
      @download="downloadOpen = true"
      @share="shareOpen = true"
      @describe="emit('describe')"
      @content="emit('content')"
      @chart="openChart"
      @create-table="openCreateTable"
    />

    <AppBanner
      v-if="rowsQuery.isError.value"
      tone="error"
      class="data-grid__state"
      data-testid="grid-error"
    >
      <div class="data-grid__error">
        <span>{{ messageOf(rowsQuery.error.value, "Could not read the rows") }}</span>
        <div class="data-grid__error-actions">
          <AppButton
            variant="secondary"
            label="Reset query"
            size="sm"
            data-testid="grid-reset-query"
            @click="resetQuery"
          />
          <AppButton
            variant="secondary"
            label="Retry"
            size="sm"
            data-testid="grid-retry"
            @click="retry"
          />
        </div>
      </div>
    </AppBanner>
    <AppBanner
      v-if="!rowsQuery.isError.value && insertError"
      tone="error"
      class="data-grid__insert-error"
      data-testid="grid-insert-error"
    >
      {{ insertError }}
    </AppBanner>

    <div
      v-if="!rowsQuery.isError.value"
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
                'data-grid__sortable': columnIsSortable(header.column.id),
                'data-grid__pinned': header.column.getIsPinned() === 'start',
              }"
              :style="columnStyle(header.column)"
            >
              <button
                type="button"
                class="data-grid__column-name"
                :aria-label="`Select column ${header.column.id}`"
                :data-testid="`grid-column-select-${header.column.id}`"
                @click="selectColumn(header.column.id)"
              >
                {{ header.column.id }}
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
                  :tooltip="`Sort by ${header.column.id}`"
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
                  :tooltip="`Hide ${header.column.id}`"
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
                  'data-grid__null': presentCell(cell).tone === 'null',
                  'data-grid__monospace': presentCell(cell).monospace === true,
                }"
              >{{ presentCell(cell).text }}</span>
              <AppIconButton
                v-for="reference in cellReferences(cell)"
                :key="reference.name"
                class="data-grid__follow"
                icon="arrow_forward"
                :tooltip="`Go to ${reference.target_title}`"
                :disable="followReference.isPending.value"
                :data-testid="`grid-follow-${row.id}-${reference.name}`"
                @click.stop="follow(row.original, reference)"
                @dblclick.stop
              />
            </td>
          </tr>
          <RowInsertRow
            v-if="insertOpen"
            ref="insertForm"
            :columns="insertGridColumns"
            :row-number="offset + rows.length + 1"
            :saving="insertRow.isPending.value"
            @save="saveInsert"
            @cancel="cancelInsert"
            @paste="pasteIntoInsert"
          />
        </tbody>
      </table>
      <AppEmptyState
        v-if="result !== undefined && rows.length === 0 && !insertOpen"
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
    <ShareDialog
      v-if="shareOpen"
      v-model="shareOpen"
      :connector-id="connectorId"
      :node-id="nodeId"
      :node-label="title"
      :view="sharedViewOfThisGrid"
    />

    <DownloadDialog
      v-if="downloadOpen && result !== undefined"
      :model-value="true"
      :page-range="range"
      :column-count="visibleGridColumns.length"
      :filter-count="queryState.filters.length"
      :all-supported="result.export_supported === true"
      :all-reason="result.export_reason ?? undefined"
      :running="downloadPage.isPending.value || exportRows.isPending.value"
      @run="runDownload"
      @update:model-value="downloadOpen = false"
    />
    <ImportDialog
      v-if="importOpen"
      :model-value="true"
      :connector-id="connectorId"
      :node-id="nodeId"
      :target-columns="importColumns"
      :running="importRows.isPending.value"
      :error="importError"
      @run="bringIn"
      @update:model-value="importOpen = false"
    />
    <CreateTableDialog
      v-if="createTableOpen && result !== undefined"
      :model-value="true"
      :source-title="title ?? nodeId"
      :source-columns="result.columns"
      :running="createRelation.isPending.value"
      :error="createTableError"
      @run="createTable"
      @update:model-value="createTableOpen = false"
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

/* A relationship is a cell control, not content. It occupies the corner
   without changing the row height or the width of the value. */
.data-grid__follow {
  position: absolute;
  inset-block-start: 0;
  inset-inline-end: 0;
  z-index: var(--dp-layer-sticky);
}

.data-grid__insert-error {
  margin: 8px 12px;
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
