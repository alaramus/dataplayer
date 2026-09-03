<script setup lang="ts">
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  toRef,
  useTemplateRef,
  watch,
} from "vue"

import type {
  FetchColumn,
  FetchReference,
  FetchRequest,
  ReferencedRows,
  RowCommand,
  RowsView,
  Sort,
} from "@/client"
import { messageOf, statusOf } from "@/shared/api/errors"
import { readText } from "@/shared/clipboard"
import {
  AppBanner,
  AppButton,
  AppIconButton,
  AppTooltip,
  useConfirm,
  useToast,
} from "@/shared/ui"

import {
  useCreateRelationFromSource,
  useDeleteRows,
  useRunRowCommand,
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
import AutoRefreshButton from "./AutoRefreshButton.vue"
import {
  loadRefreshSeconds,
  refreshHeldBy,
  saveRefreshSeconds,
  startingRefresh,
} from "./autoRefresh"
import type { RefreshSeconds } from "./autoRefresh"
import { useSourceChangesStore } from "@/stores/sourceChanges"

import { commandOutcome, commandQuestion, keysOf } from "./rowCommands"
import CellEditorDialog from "./CellEditorDialog.vue"
import CreateTableDialog from "./CreateTableDialog.vue"
import { fromTsv } from "./clipboard"
import { defaultColumnLayout } from "./columnLayout"
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
import ImportDialog from "./ImportDialog.vue"
import RowInsertRow from "./RowInsertRow.vue"
import type { InsertGridColumn } from "./RowInsertRow.vue"
import { toGridRows } from "./model"
import { keyValues, referencesLedBy } from "./references"
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
import { planPaste, planRowPaste } from "./paste"
import type { PasteColumn } from "./paste"
import TabularGrid from "./TabularGrid.vue"
import { tabularColumns } from "./tabular"
import type {
  TabularEditRequest,
  TabularPasteRequest,
  TabularVisibleColumn,
} from "./tabular"
import type {
  Filter,
  GridQueryState,
  GridRow,
  PageCommand,
  PageSize,
  StoredGridState,
} from "./types"

const props = defineProps<{
  connectorId: string
  nodeId: string
  title?: string
  canDescribe?: boolean
  /** Whether this source will write a statement about this node (D65). */
  canQuery?: boolean
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
  /** Open a console on this relation, with SQL the source wrote. */
  query: []
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
const tableColumns = computed(() => tabularColumns(result.value?.columns ?? []))
const visibleGridColumns = ref<TabularVisibleColumn[]>([])
const downloadColumns = ref<TabularVisibleColumn[]>([])
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
const tabularGrid = useTemplateRef<{
  clearSelection: () => void
  focus: (selector: string) => void
}>("tabularGrid")
const insertForm = useTemplateRef<{
  fill: (values: { column: string; value: string | null }[]) => void
}>("insertForm")
const canInsert = computed(() => result.value?.insert_supported === true)
const editableRowIds = computed(() =>
  rows.value.flatMap((row, index) =>
    typeof result.value?.row_handles?.[index] === "string" ? [row.id] : []
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
  queryAwaitingPersistence.value = next
  queryState.value = next
}

function changeSort(sort: Sort[]) {
  const next = withSort(queryState.value, sort)
  queryAwaitingPersistence.value = next
  queryState.value = next
}

function changeLayout(next: ColumnLayoutState) {
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
      ? { ...defaultColumnLayout(tabularColumns(serverColumns ?? [])), filters: [], sort: [] }
      : serverColumns === undefined
        ? stored
        : reconcileGridState(stored, serverColumns)
  saveGridState(props.connectorId, props.nodeId, {
    ...base,
    filters: state.filters,
    sort: state.sort,
  })
}

/**
 * Put a copied block back, from the top-left of the selection.
 *
 * Everything that can be known here is checked here — where the block lands,
 * whether it fits, whether those columns may be edited — and everything that
 * cannot is the source's answer: whether the rows still hold their version,
 * and whether each value can be read as its column's type.
 */
async function pasteSelection(request: TabularPasteRequest) {
  const pasteColumns: PasteColumn[] = request.columns.map((column) => ({
    name: column.id,
    valueIndex: column.valueIndex,
    editable:
      result.value?.columns.find((candidate) => candidate.name === column.id)?.editable ===
      true,
  }))
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
    pasteColumns,
    {
      rowIndex: request.bounds.minRowIndex,
      columnIndex: request.bounds.minColumnIndex,
    }
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
const insertGridColumns = computed<InsertGridColumn[]>(() =>
  visibleGridColumns.value.flatMap((entry) => {
    const column = result.value?.columns.find((candidate) => candidate.name === entry.id)
    return column === undefined
      ? []
      : [{ column, pinned: entry.pinned, style: entry.style }]
  })
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

function openEditor(request: TabularEditRequest) {
  const column = result.value?.columns.find(
    (candidate) => candidate.name === request.column.id
  )
  const rowHandle = result.value?.row_handles?.[request.rowIndex]
  if (column?.editable !== true || typeof rowHandle !== "string") return
  editError.value = ""
  editor.value = { column, value: request.value, rowHandle }
}

async function runDownload(scope: DownloadScope) {
  if (result.value === undefined || downloadColumns.value.length === 0) return
  const fallback = `${props.title ?? "table"}.csv`
  try {
    if (scope === "all") {
      const exported = await exportRows.mutateAsync({
        node_id: props.nodeId,
        title: props.title ?? "table",
        columns: downloadColumns.value.map((column) => column.id),
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
      columns: downloadColumns.value.map((column) => column.id),
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

function openDownload(columns: TabularVisibleColumn[]): void {
  downloadColumns.value = [...columns]
  downloadOpen.value = true
}

function openChart(columns: TabularVisibleColumn[]): void {
  if (result.value === undefined || columns.length === 0) return
  emit(
    "chart",
    { ...request.value, filters: [...queryState.value.filters], sort: [...queryState.value.sort] },
    columns.map((column) => column.id)
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
function cellReferences(columnId: string, value: string | null): FetchReference[] {
  if (value === null) return NO_REFERENCES
  return referencesByColumn.value.get(columnId) ?? NO_REFERENCES
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
  tabularGrid.value?.focus('[data-testid^="grid-insert-value-"]')
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

function selectedRowHandles(indexes: number[]): string[] {
  const selected = indexes.map((index) => result.value?.row_handles?.[index])
  return selected.every((handle): handle is string => typeof handle === "string")
    ? selected
    : []
}

function canDeleteRows(indexes: number[]): boolean {
  return (
    result.value?.delete_supported === true &&
    indexes.length > 0 &&
    selectedRowHandles(indexes).length === indexes.length
  )
}

async function deleteSelection(indexes: number[]) {
  const handles = selectedRowHandles(indexes)
  if (!canDeleteRows(indexes) || handles.length === 0) return
  const accepted = await confirm({
    title: `Delete ${handles.length} ${handles.length === 1 ? "row" : "rows"}?`,
    message: "This cannot be undone.",
    confirmLabel: "Delete",
    danger: true,
  })
  if (!accepted) return
  try {
    await deleteRows.mutateAsync({ node_id: props.nodeId, row_handles: handles })
    tabularGrid.value?.clearSelection()
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
      layout.value = defaultColumnLayout(tabularColumns(serverColumns))
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
    // The interval belongs to the relation, so a tab pointed at another one
    // takes that relation's answer rather than carrying this one over. What
    // the new relation suggests arrives with its first page, below.
    suggestedFor = ""
    refreshSeconds.value = startingRefresh(
      loadRefreshSeconds(props.connectorId, props.nodeId),
      null
    )
    startTicking()
  }
)

/**
 * How often this grid re-reads itself, and what stops it.
 *
 * The timer is here rather than in the button because this is what owns the
 * fetch, and it runs whenever an interval is chosen — a tick that must not
 * fetch is skipped rather than queued. Two things make it skip: the tab is
 * not on screen, and the user is in the middle of something. Both matter.
 * A tab kept alive behind another one would otherwise poll the source
 * forever with nobody looking, and a poll landing while a cell is being
 * edited would throw away what was typed.
 */
const refreshSeconds = ref<RefreshSeconds | null>(
  startingRefresh(loadRefreshSeconds(props.connectorId, props.nodeId), null)
)
/** Whether this panel is the one its section is showing. */
const panelShown = ref(true)
/** Whether the browser window is showing this document at all. */
const windowShown = ref(true)
const onScreen = computed(() => panelShown.value && windowShown.value)

const refreshHeld = computed(() =>
  refreshHeldBy({
    fetching: rowsQuery.isFetching.value,
    editing: editor.value !== null,
    inserting: insertOpen.value,
    selecting: selectedRows.value.length > 0,
    away: !onScreen.value,
  })
)

let ticking: ReturnType<typeof setInterval> | undefined

function stopTicking() {
  if (ticking === undefined) return
  clearInterval(ticking)
  ticking = undefined
}

function startTicking() {
  stopTicking()
  const seconds = refreshSeconds.value
  if (seconds === null) return
  ticking = setInterval(() => {
    if (refreshHeld.value !== null) return
    void refreshRows()
  }, seconds * 1000)
}

function chooseRefresh(seconds: RefreshSeconds | null) {
  refreshSeconds.value = seconds
  saveRefreshSeconds(props.connectorId, props.nodeId, seconds)
  startTicking()
  // Turning it on reads at once: waiting five seconds for the first answer
  // reads as a button that did nothing.
  if (seconds !== null && refreshHeld.value === null) void refreshRows()
}

function noteWindow() {
  windowShown.value = document.visibilityState === "visible"
}

/**
 * The interval this relation suggests, taken once, and only if nobody has
 * said otherwise about this relation before.
 *
 * Not saved: it is a default rather than a decision, and writing it down
 * would make the source's opinion look like the person's own the next time
 * the source changed its mind (D70).
 */
let suggestedFor = ""

watch(
  () => [props.connectorId, props.nodeId, result.value?.refresh_seconds] as const,
  ([connectorId, nodeId, suggested]) => {
    const key = `${connectorId}\u0000${nodeId}`
    if (suggestedFor === key || suggested === undefined) return
    suggestedFor = key
    if (loadRefreshSeconds(connectorId, nodeId) !== undefined) return
    const start = startingRefresh(undefined, suggested)
    if (start === null) return
    refreshSeconds.value = start
    startTicking()
  },
  { immediate: true }
)

/**
 * Whether the source offers one of the page's own commands here.
 *
 * The vocabulary is the source's to withdraw from (D72): a report is the
 * server describing what it is doing, not data somebody is keeping, so
 * charting it or making a table of it are answers to a question nobody asked
 * of it. A page that says nothing offers everything.
 */
function offers(command: PageCommand): boolean {
  return result.value?.page_commands?.includes(command) ?? false
}

/**
 * What one source-declared command over rows would be given (D70).
 *
 * Nothing here knows what a command means: which column names a row came
 * from the answer that offered it, and the keys are the values in that
 * column of the rows somebody ticked.
 */
const selectedRows = ref<number[]>([])
const runRowCommand = useRunRowCommand(toRef(props, "connectorId"))
const changes = useSourceChangesStore()

function keysFor(command: RowCommand): string[] {
  return keysOf(command, result.value?.columns ?? [], rows.value, selectedRows.value)
}

async function runCommand(command: RowCommand) {
  const keys = keysFor(command)
  if (keys.length === 0) return
  if (command.destructive) {
    const accepted = await confirm({
      title: commandQuestion(command, keys),
      message: command.description,
      confirmLabel: command.title,
      danger: true,
    })
    if (!accepted) return
  }
  try {
    const outcome = commandOutcome(
      await runRowCommand.mutateAsync({
        node_id: props.nodeId,
        name: command.name,
        keys,
      })
    )
    tabularGrid.value?.clearSelection()
    // An extension installed here brings schemas and types with it, and the
    // catalog column holds its rows itself. Which commands leave the source
    // different is the source's own answer, carried on the command (D66).
    if (command.changes_structure) changes.announce(props.connectorId)
    if (outcome.failed) toast.error(outcome.text)
    else toast.success(outcome.text)
  } catch (cause) {
    toast.error(messageOf(cause, `${command.title} could not be done`))
  }
}

// Coming back to a tab that has been refreshing shows what is there now,
// rather than what was there when it was left. Covers both ways of being
// away, which is why it watches the two together.
watch(onScreen, (shown) => {
  if (!shown || refreshSeconds.value === null || refreshHeld.value !== null) return
  void refreshRows()
})

onMounted(() => {
  noteWindow()
  document.addEventListener("visibilitychange", noteWindow)
  startTicking()
})
onActivated(() => {
  panelShown.value = true
})
onDeactivated(() => {
  panelShown.value = false
})
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", noteWindow)
  stopTicking()
})

defineExpose({
  reload: async () => {
    await refreshRows()
  },
})
</script>

<template>
  <TabularGrid
    ref="tabularGrid"
    :columns="tableColumns"
    :rows="rows"
    :page="queryState.page"
    :page-size="queryState.pageSize"
    :filters="queryState.filters"
    :sort="queryState.sort"
    :layout="layout"
    :has-more="result?.has_more === true"
    :loading="rowsQuery.isPending.value"
    :refreshing="rowsQuery.isFetching.value && result !== undefined"
    :error="rowsQuery.isError.value ? messageOf(rowsQuery.error.value, 'Could not read the rows') : ''"
    :empty-text="insertOpen ? '' : 'No rows'"
    :update-reason="result?.update_reason ?? ''"
    :editable-row-ids="editableRowIds"
    @update:page-size="changePageSize"
    @update:filters="changeFilters"
    @update:sort="changeSort"
    @update:layout="changeLayout"
    @turn-page="turnPage"
    @retry="retry"
    @reset="resetQuery"
    @paste="pasteSelection"
    @edit="openEditor"
    @visible-columns="visibleGridColumns = $event"
    @selection="selectedRows = $event"
  >
    <template
      #commands="{
        canCopy,
        selectedRowIndexes,
        visibleColumns,
        requestPaste,
      }"
    >
      <AutoRefreshButton
        v-if="result !== undefined"
        :seconds="refreshSeconds"
        :held="refreshHeld"
        @update:seconds="chooseRefresh"
      />
      <AppIconButton
        v-if="canInsert && importColumns.length > 0"
        icon="input"
        tooltip="Bring rows in"
        data-testid="grid-import"
        @click="openImport"
      />
      <AppIconButton
        v-if="result?.update_supported === true"
        icon="content_paste"
        tooltip="Paste into the selection"
        :disable="!canCopy"
        data-testid="grid-paste"
        @click="requestPaste"
      />
      <AppIconButton
        v-if="offers('download') && visibleColumns.length > 0"
        icon="download"
        tooltip="Download"
        :disable="downloadPage.isPending.value || exportRows.isPending.value"
        :loading="downloadPage.isPending.value || exportRows.isPending.value"
        data-testid="grid-download"
        @click="openDownload(visibleColumns)"
      />
      <AppIconButton
        v-if="offers('share')"
        icon="share"
        tooltip="Share this view"
        data-testid="grid-share"
        @click="shareOpen = true"
      />
      <AppIconButton
        v-if="offers('chart') && visibleColumns.length > 0"
        icon="insert_chart"
        tooltip="Charts"
        data-testid="grid-charts"
        @click="openChart(visibleColumns)"
      />
      <AppIconButton
        v-if="offers('create_relation') && result !== undefined && result.columns.length > 0"
        icon="post_add"
        tooltip="Create table from these rows"
        data-testid="grid-create-table"
        @click="openCreateTable"
      />
      <AppIconButton
        v-if="contentTitle"
        icon="code"
        :tooltip="contentTitle"
        data-testid="grid-content"
        @click="emit('content')"
      />
      <AppIconButton
        v-if="canQuery && offers('query')"
        icon="terminal"
        tooltip="Open as a query"
        data-testid="grid-query"
        @click="emit('query')"
      />
      <AppIconButton
        v-if="canDescribe"
        icon="account_tree"
        tooltip="Structure"
        data-testid="grid-structure"
        @click="emit('describe')"
      />
      <span
        v-if="result?.insert_supported === true"
        data-testid="grid-insert-command"
      >
        <AppIconButton
          icon="add"
          tooltip="Insert row"
          :disable="!canInsert"
          data-testid="grid-insert"
          @click="openInsert"
        />
      </span>
      <!-- What the source itself offers to do to the rows that are ticked.
           Labelled rather than iconed: an icon per command would be a table
           of names on this side, which is exactly what the source declaring
           them exists to avoid (D70). -->
      <span
        v-for="command in result?.row_commands ?? []"
        :key="command.name"
        :data-testid="`grid-row-command-${command.name}`"
      >
        <AppButton
          :variant="command.destructive ? 'danger-quiet' : 'quiet'"
          size="sm"
          :label="command.title"
          :disable="keysFor(command).length === 0 || runRowCommand.isPending.value"
          :data-testid="`grid-row-command-run-${command.name}`"
          @click="runCommand(command)"
        >
          <AppTooltip>{{ command.description }}</AppTooltip>
        </AppButton>
      </span>

      <span
        v-if="result?.delete_supported === true"
        data-testid="grid-delete-command"
      >
        <AppIconButton
          icon="remove"
          :tooltip="
            selectedRowIndexes.length > 0
              ? `Delete ${selectedRowIndexes.length} selected rows`
              : 'Delete selected rows'
          "
          :disable="!canDeleteRows(selectedRowIndexes)"
          data-testid="grid-delete"
          @click="deleteSelection(selectedRowIndexes)"
        />
      </span>
    </template>

    <template #before-grid>
      <AppBanner
        v-if="!rowsQuery.isError.value && insertError"
        tone="error"
        class="data-grid__insert-error"
        data-testid="grid-insert-error"
      >
        {{ insertError }}
      </AppBanner>
    </template>

    <template #cell-overlay="{ row, column, value }">
      <AppIconButton
        v-for="reference in cellReferences(column.id, value)"
        :key="reference.name"
        class="data-grid__follow"
        icon="arrow_forward"
        :tooltip="`Go to ${reference.target_title}`"
        :disable="followReference.isPending.value"
        :data-testid="`grid-follow-${row.id}-${reference.name}`"
        @click.stop="follow(row, reference)"
        @dblclick.stop
      />
    </template>

    <template #after-rows="{ nextRowNumber }">
      <RowInsertRow
        v-if="insertOpen"
        ref="insertForm"
        :columns="insertGridColumns"
        :row-number="nextRowNumber"
        :saving="insertRow.isPending.value"
        @save="saveInsert"
        @cancel="cancelInsert"
        @paste="pasteIntoInsert"
      />
    </template>

    <template #after-grid>
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
        :column-count="downloadColumns.length"
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
    </template>
  </TabularGrid>
</template>

<style scoped>
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
</style>
