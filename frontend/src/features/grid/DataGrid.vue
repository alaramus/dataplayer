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
  FetchRequest,
  FetchResult,
  ReferencedRows,
  RowCommand,
  RowsView,
  Sort,
} from "@/client"
import { errorKindOf, messageOf, statusOf } from "@/shared/api/errors"
import ActionDialog from "@/features/catalog/ActionDialog.vue"
import { reloadedBy, toCommands } from "@/features/catalog/actions"
import type { ActionCommand, ActionOutcome } from "@/features/catalog/actions"
import { useNodeActions } from "@/features/catalog/api"
import { useConnectionFreshness } from "@/features/connectors/api"
import { useServerLeaveGuard } from "@/shared/servers/leaving"
import { readText } from "@/shared/clipboard"
import {
  AppBanner,
  AppButton,
  AppIconButton,
  AppMenu,
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
  useKeepPage,
  useKeepRows,
  useForgetRowsPage,
  useInsertRow,
  useRowsPage,
  useUpdateCell,
  useUpdateCells,
} from "./api"
import AutoRefreshButton from "./AutoRefreshButton.vue"
import { NOT_OFFERED, NOT_YET, tipOf } from "./toolbar"
import type { Unavailable } from "./toolbar"
import {
  loadRefreshSeconds,
  refreshHeldBy,
  saveRefreshSeconds,
  startingRefresh,
} from "./autoRefresh"
import type { RefreshSeconds } from "./autoRefresh"
import { useSourceChangesStore } from "@/stores/sourceChanges"

import { commandOutcome, commandQuestion, commandsForRow, keyOf } from "./rowCommands"
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
import type { DownloadDestination, DownloadScope } from "./download"
import DownloadDialog from "./DownloadDialog.vue"
import ShareDialog from "@/features/shares/ShareDialog.vue"
import { useLockedKey } from "@/features/sshKeys/api"
import UnlockKeyButton from "@/features/sshKeys/UnlockKeyButton.vue"
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
import { useReferences } from "./useReferences"
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
defineSlots<{
  /** The end of the row of commands, where a panel puts what it offers (D112). */
  "commands-end"(): unknown
  /** The far end of the row the pager is on, passed through to the grid. */
  "pager-start"(): unknown
}>()
const emit = defineEmits<{
  describe: []
  content: []
  /** Open a console on this relation, with SQL the source wrote. */
  query: []
  chart: [request: FetchRequest, columns: string[]]
  follow: [target: ReferencedRows]
  /** Read one row downwards, in a panel of its own (D111). */
  record: [value: { request: FetchRequest; index: number }]
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
/** The key this connection signs in with, when reading the rows found it locked (D147). */
const lockedKey = useLockedKey(
  () => props.connectorId,
  () => errorKindOf(rowsQuery.error.value)
)

async function refreshRows() {
  refreshNext.value = true
  try {
    await rowsQuery.refetch()
  } finally {
    refreshNext.value = false
  }
}
const result = computed(() => rowsQuery.data.value?.page)
// Where this page came from, and how long this connection may keep one. Both
// belong to the badge above the grid, which is the only thing on the screen
// that can say the rows are older than they look (D105).
const freshness = computed(() => rowsQuery.data.value?.freshness)
const { keepsAnswers, cacheWindow } = useConnectionFreshness(
  toRef(props, "connectorId")
)
const rows = computed(() =>
  result.value === undefined || rowsQuery.isError.value
    ? []
    : toGridRows(result.value, request.value.offset ?? 0)
)
const layout = ref<ColumnLayoutState>({ ...EMPTY_LAYOUT })

/**
 * What the source last said about this relation, kept through a refusal (U02).
 *
 * A page of rows and the description of what holds them arrive as one answer,
 * so a request the source refused used to leave no columns and every
 * capability false. Filters and Sort then greyed themselves out saying this
 * source does not filter or sort rows - and the filter editor, the one place a
 * mistyped value could be corrected, unmounted with them. What a relation can
 * do does not change because one page of it was refused.
 */
const lastAnswer = ref<{ node: string; page: FetchResult } | null>(null)
watch(
  [result, () => props.nodeId] as const,
  ([page, node]) => {
    if (page !== undefined) lastAnswer.value = { node, page }
  },
  // A tab returned to is answered from the client's cache, so the page is
  // already here and never changes again: without this the grid would come
  // back with no columns at all.
  { immediate: true }
)
/** Another relation is described by its own answer, never by the one before it. */
const described = computed(() =>
  lastAnswer.value?.node === props.nodeId ? lastAnswer.value.page : null
)
const tableColumns = computed(() => tabularColumns(described.value?.columns ?? []))
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
const keepPage = useKeepPage(toRef(props, "connectorId"))
const keepRows = useKeepRows(toRef(props, "connectorId"))
const importRows = useImportRows(toRef(props, "connectorId"))
const createRelation = useCreateRelationFromSource()
/**
 * The ways in and out of a row, shared with every screen that shows one.
 *
 * Which columns are on screen is this grid's business; what a key means and
 * where it leads is the source's, and asking it is written once (D36, D110).
 */
const { cellReferences, cellArriving, follow, followBack, isPending: jumping } =
  useReferences({
    connectorId: toRef(props, "connectorId"),
    nodeId: toRef(props, "nodeId"),
    columns: computed(() => result.value?.columns ?? []),
    visible: computed(() => visibleGridColumns.value.map((column) => column.id)),
    references: computed(() => result.value?.references ?? []),
    onFollow: (target) => emit("follow", target),
  })
const forgetRowsPage = useForgetRowsPage(toRef(props, "connectorId"))
useServerLeaveGuard(async () => {
  if ([updateCell, updateCells, insertRow, deleteRows, importRows, createRelation].some((mutation) => mutation.isPending.value)) {
    toast.info("Wait for the table change to finish before switching servers")
    return false
  }
  if (editor.value === null && !insertOpen.value && !importOpen.value && !createTableOpen.value) return true
  return await confirm({
    title: "Leave the unfinished table form?",
    message: "An edit, insertion or import form is still open. Its unapplied values will be lost when switching servers.",
    confirmLabel: "Leave form",
    danger: true,
  })
})
const tabularGrid = useTemplateRef<{
  clearSelection: () => void
  focus: (selector: string) => void
}>("tabularGrid")
const insertForm = useTemplateRef<{
  fill: (values: { column: string; value: string | null }[]) => void
}>("insertForm")
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
    // The destination may be the very connection the catalog beside this is
    // showing — a folder of the source these rows came from — and a list that
    // built itself does not re-read on a cache being emptied (D66).
    changes.announce(value.connectorId)
    toast.success(`Created ${answer.node.name} with ${answer.inserted} rows`)
  } catch (error) {
    createTableError.value = messageOf(error, "The new table or file could not be created")
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

/**
 * Write the table out, to one of two places.
 *
 * Four combinations of scope and destination, and each of them is one request:
 * the server writes the same CSV either way and the destination decides
 * whether the answer is the file or a sentence about where it went (D28).
 */
async function runDownload(scope: DownloadScope, destination: DownloadDestination) {
  if (result.value === undefined || downloadColumns.value.length === 0) return
  const title = props.title ?? "table"
  const columns = downloadColumns.value.map((column) => column.id)
  const whole = {
    node_id: props.nodeId,
    title,
    columns,
    filters: [...queryState.value.filters],
    sort: [...queryState.value.sort],
  }
  const page = { ...request.value, title, columns }
  try {
    if (destination === "files") {
      const kept =
        scope === "all"
          ? await keepRows.mutateAsync(whole)
          : await keepPage.mutateAsync(page)
      downloadOpen.value = false
      toast.success(`${kept.row_count} rows saved to your files as ${kept.filename}`)
      return
    }
    if (scope === "all") {
      // Followed as a plain browser download rather than read here: a whole
      // relation must not be assembled in this tab's memory.
      const exported = await exportRows.mutateAsync(whole)
      saveNativeDownload(exported.download_url)
      downloadOpen.value = false
      toast.success(`${exported.row_count} rows downloaded`)
      return
    }
    const downloaded = await downloadPage.mutateAsync(page)
    saveBrowserDownload(
      downloaded.blob,
      filenameFromDisposition(downloaded.disposition, `${title}.csv`)
    )
    downloadOpen.value = false
    toast.success("Page downloaded")
  } catch (error) {
    toast.error(messageOf(error, "Could not write this table out"))
  }
}

/** Any of the four requests is under way, and the toolbar says so once. */
const writingOut = computed(
  () =>
    downloadPage.isPending.value ||
    exportRows.isPending.value ||
    keepPage.isPending.value ||
    keepRows.isPending.value
)

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

/**
 * Which row of which page, in the words the panel reads it back with.
 *
 * The request travels rather than the values: the row view reads the same page
 * through the same query key, so opening a row costs no request at all and the
 * two stay in step. The id of a grid row is its place in the relation, and the
 * page's own offset turns that back into a place in the page.
 */
function openRecord(row: GridRow) {
  emit("record", {
    request: { ...request.value },
    index: Number(row.id) - (request.value.offset ?? 0),
  })
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
 * column renamed or dropped leaves a stored query the source refuses every
 * time. Rather than reading the refusal, the grid asks again without filters
 * or sorting and keeps back everything the fresh answer still knows about.
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
 * Both halves of a link go through `reconcileGridState`, which a tab restored
 * from storage also uses, so a column the relation no longer has is dropped in
 * one place and said rather than silently missing (D60). Waiting for the
 * columns first: a filter naming a gone column would be sent and refused.
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
 * How often this grid re-reads itself, and what stops it. The timer is here
 * rather than in the button because this is what owns the fetch.
 *
 * A tick that must not fetch is skipped rather than queued, for two reasons: a
 * tab kept alive behind another would otherwise poll the source forever with
 * nobody looking, and a poll landing while a cell is being edited would throw
 * away what was typed.
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
  const page = result.value
  if (page === undefined) return false
  return page.page_commands?.includes(command) ?? true
}

/**
 * Why each command of this row is off, or null while it is not.
 *
 * Every one of them was a `v-if` until now: a command the source cannot do
 * simply was not drawn, so the row changed shape between a table and a file
 * and no button had a place a person could learn. They are all disabled with
 * a sentence instead — the answer the command bar already gives (D69).
 *
 * The order inside each is the order of the answers: what the source will
 * never do outranks what is merely missing this second, because "tick a row"
 * under a button that will never delete anything is a lie.
 */
/**
 * What stands between a command and the rows it would act on, before the
 * command's own conditions (U02).
 *
 * Ordered the way the sentences themselves are: the source's own answer
 * outranks anything momentary, because "tick a row first" about a source that
 * never deletes one is a lie. Until something has been read there is no answer
 * to give, and a refused page leaves the answer standing but no rows under it.
 */
function whatStopsIt(
  offered: (page: FetchResult) => boolean,
  unsupportedSays: string
): Unavailable {
  const page = described.value
  if (page === null) return NOT_YET.reading
  if (!offered(page)) return unsupportedSays
  return rowsQuery.isError.value ? NOT_YET.unread : null
}

const chartReason = computed<Unavailable>(() => {
  if (!offers("chart")) return NOT_OFFERED.chart
  if (rowsQuery.isError.value) return NOT_YET.unread
  return visibleGridColumns.value.length === 0 ? NOT_YET.noColumns : null
})

const downloadReason = computed<Unavailable>(() => {
  if (!offers("download")) return NOT_OFFERED.download
  if (rowsQuery.isError.value) return NOT_YET.unread
  return visibleGridColumns.value.length === 0 ? NOT_YET.noColumns : null
})

const keepReason = computed<Unavailable>(() => {
  if (!offers("create_relation")) return NOT_OFFERED.keep
  // The dialog reads the columns of the answer in hand, so this one waits for
  // a page rather than for a description of one.
  if (result.value === undefined) {
    return described.value === null ? NOT_YET.reading : NOT_YET.unread
  }
  return result.value.columns.length === 0 ? NOT_YET.noColumns : null
})

const importReason = computed<Unavailable>(() => {
  const stopped = whatStopsIt((page) => page.insert_supported === true, NOT_OFFERED.import)
  if (stopped !== null) return stopped
  return importColumns.value.length === 0 ? NOT_OFFERED.import : null
})

const insertReason = computed<Unavailable>(() =>
  whatStopsIt((page) => page.insert_supported === true, NOT_OFFERED.insert)
)

/** Taken as a function: what may be pasted is the grid's own selection. */
function pasteReason(canCopy: boolean): Unavailable {
  const stopped = whatStopsIt((page) => page.update_supported === true, NOT_OFFERED.paste)
  if (stopped !== null) return stopped
  return canCopy ? null : NOT_YET.noSelection
}

function deleteReason(selected: readonly number[]): Unavailable {
  const stopped = whatStopsIt((page) => page.delete_supported === true, NOT_OFFERED.remove)
  if (stopped !== null) return stopped
  return canDeleteRows([...selected]) ? null : NOT_YET.noRowsPicked
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

/**
 * Whether a row of this opens on its own, downwards (D111).
 *
 * The source's answer: an ordinary relation holds rows, and a report holds a
 * statement's output — where the row view would be these same values in a
 * column, with no model and no key to offer beside them. Missing on a page
 * read before the question existed, which is the ordinary case rather than a
 * refusal.
 */
const canOpenRecord = computed(() => result.value?.record_supported !== false)

/**
 * What this row offers, which is not the same on every row (D70).
 *
 * A command may belong only where the row's own value admits it: an extension
 * is installed or removed, never both. Which rows, like which column names
 * one, is the source's answer.
 */
function commandsFor(row: GridRow): RowCommand[] {
  return commandsForRow(
    result.value?.row_commands ?? [],
    result.value?.columns ?? [],
    row
  )
}

/**
 * What the source offers to do to this node from above its own rows (D79).
 *
 * The same actions the catalog menu holds, asked the same way; which of them
 * belong here is the source's answer and not a name this side knows. A new
 * role is asked for over the list of roles, where the rows it joins are.
 */
const nodeActions = useNodeActions(
  toRef(props, "connectorId"),
  computed(() => [props.nodeId])
)
const rowActions = computed<ActionCommand[]>(() =>
  toCommands(
    (nodeActions.data.value ?? []).filter(
      (action) => action.offered_in === "rows" && action.applicable
    )
  )
)
const openAction = ref<ActionCommand | null>(null)

/**
 * What is left to do once an action run from here has finished.
 *
 * Not to say what happened: the window said it, in the source's own words,
 * and a second line saying it again is a second line. What is left is the
 * page — a role added to this list names no branch of the catalog to re-read
 * (D79), so nothing else on screen would ever show it.
 */
async function actionDone(outcome: ActionOutcome) {
  if (outcome.done.length === 0) return
  if (reloadedBy(outcome).length > 0) changes.announce(props.connectorId)
  await refreshRows()
}

async function runCommand(command: RowCommand, row: GridRow) {
  const key = keyOf(command, result.value?.columns ?? [], row)
  if (key === null) return
  if (command.destructive) {
    const accepted = await confirm({
      title: commandQuestion(command, key),
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
        keys: [key],
      })
    )
    // An extension installed here brings schemas and types with it, and the
    // catalog column holds its rows itself. Which commands leave the source
    // different is the source's own answer, carried on the command (D66).
    if (command.changes_structure) changes.announce(props.connectorId)
    if (outcome.failed) toast.error(outcome.text)
    else toast.success(outcome.text)
    // The row it was run on is what changed, and the button that ran it is
    // drawn from that row: an extension that has just been installed must
    // stop offering to be installed again.
    await refreshRows()
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
  /**
   * How old this page is, for the reload button the panel draws.
   *
   * Undefined where an answer could not be older than the read, so that
   * button stays a plain refresh with nothing to report (D105). The grid owns
   * the query and therefore the answer; the tab owns the row of commands, so
   * the two meet here.
   */
  freshness: computed(() => (keepsAnswers.value ? freshness.value : undefined)),
  cacheWindow,
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
      v-if="lockedKey"
      #error-actions
    >
      <UnlockKeyButton
        :ssh-key="lockedKey"
        variant="secondary"
        size="sm"
      />
    </template>
    <!-- Read as something else: each of these opens a tab of its own on the
         same rows, which is what puts them together. -->
    <template #commands-open="{ visibleColumns }">
      <AppIconButton
        icon="account_tree"
        :tooltip="tipOf('Structure', canDescribe ? null : NOT_OFFERED.structure)"
        :disable="!canDescribe"
        data-testid="grid-structure"
        @click="emit('describe')"
      />
      <AppIconButton
        icon="terminal"
        :tooltip="tipOf('Open as a query', canQuery && offers('query') ? null : NOT_OFFERED.query)"
        :disable="!(canQuery && offers('query'))"
        data-testid="grid-query"
        @click="emit('query')"
      />
      <AppIconButton
        icon="code"
        :tooltip="contentTitle ?? tipOf('Open as a document', NOT_OFFERED.document)"
        :disable="!contentTitle"
        data-testid="grid-content"
        @click="emit('content')"
      />
      <AppIconButton
        icon="insert_chart"
        :tooltip="tipOf('Charts', chartReason)"
        :disable="chartReason !== null"
        data-testid="grid-charts"
        @click="openChart(visibleColumns)"
      />
    </template>

    <!-- Out of the grid: a clipboard, a file, a link, a relation of its own.
         None of them writes to the source. -->
    <template #commands-out="{ visibleColumns }">
      <AppIconButton
        icon="download"
        :tooltip="tipOf('Download', downloadReason)"
        :disable="downloadReason !== null || writingOut"
        :loading="writingOut"
        data-testid="grid-download"
        @click="openDownload(visibleColumns)"
      />
      <AppIconButton
        icon="share"
        :tooltip="tipOf('Share this view', offers('share') ? null : NOT_OFFERED.share)"
        :disable="!offers('share')"
        data-testid="grid-share"
        @click="shareOpen = true"
      />
      <AppIconButton
        icon="post_add"
        :tooltip="tipOf('Keep these rows as a new table or file', keepReason)"
        :disable="keepReason !== null"
        data-testid="grid-create-table"
        @click="openCreateTable"
      />
    </template>

    <!-- Everything that writes to the source, and nothing else. Apart from
         the rest by a rule, which is half the reason the groups exist. -->
    <template
      #commands-write="{
        canCopy,
        selectedRowIndexes,
        requestPaste,
      }"
    >
      <AppIconButton
        icon="content_paste"
        :tooltip="tipOf('Paste into the selection', pasteReason(canCopy))"
        :disable="pasteReason(canCopy) !== null"
        data-testid="grid-paste"
        @click="requestPaste"
      />
      <AppIconButton
        icon="input"
        :tooltip="tipOf('Bring rows in', importReason)"
        :disable="importReason !== null"
        data-testid="grid-import"
        @click="openImport"
      />
      <span data-testid="grid-insert-command">
        <AppIconButton
          icon="add"
          :tooltip="tipOf('Insert row', insertReason)"
          :disable="insertReason !== null"
          data-testid="grid-insert"
          @click="openInsert"
        />
      </span>
      <span data-testid="grid-delete-command">
        <AppIconButton
          icon="remove"
          :tooltip="tipOf(
            selectedRowIndexes.length > 0
              ? `Delete ${selectedRowIndexes.length} selected rows`
              : 'Delete selected rows',
            deleteReason(selectedRowIndexes)
          )"
          :disable="deleteReason(selectedRowIndexes) !== null"
          data-testid="grid-delete"
          @click="deleteSelection(selectedRowIndexes)"
        />
      </span>

      <!-- Last in the group, after what changes the rows that are here: what
           the source offers to do to this node from over its own rows, rather
           than from behind a tick in the catalog (D79). Drawn as the picture
           the source named, like the row commands in the corner of each row;
           a source that named none is drawn by its title instead. -->
      <span
        v-for="action in rowActions"
        :key="action.name"
        :data-testid="`grid-node-action-${action.name}`"
      >
        <AppIconButton
          v-if="action.icon"
          :icon="action.icon"
          :variant="action.destructive ? 'danger-quiet' : 'quiet'"
          :tooltip="action.label"
          :data-testid="`grid-node-action-run-${action.name}`"
          @click="openAction = action"
        />
        <AppButton
          v-else
          :variant="action.destructive ? 'danger-quiet' : 'quiet'"
          size="sm"
          :label="action.label"
          :data-testid="`grid-node-action-run-${action.name}`"
          @click="openAction = action"
        />
      </span>
    </template>

    <!-- About the tab rather than about the rows: how often it re-reads
         itself, the way back to its node, the way out of a window (D112). The
         auto-refresh belongs to this grid and the rest is forwarded, so this
         is the one group with two owners. -->
    <template #commands-tab>
      <AutoRefreshButton
        :seconds="refreshSeconds"
        :held="refreshHeld"
        :disable="result === undefined"
        @update:seconds="chooseRefresh"
      />
      <slot name="commands-end" />
    </template>

    <!-- Forwarded rather than filled: what belongs on the pager's row is
         about the node the tab is on, and this grid knows nothing about it. -->
    <template #pager-start>
      <slot name="pager-start" />
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

    <template #row-actions="{ row }">
      <!-- What the source offers to do to this row, in the corner of the row
           it is about (D70): the pid is on screen already, and a button that
           needed it ticked first was a button asking for what it can see. The
           picture is the source's, because a client choosing one would be a
           table of command names on this side. -->
      <AppIconButton
        v-for="command in commandsFor(row)"
        :key="command.name"
        :icon="command.icon"
        compact
        :variant="command.destructive ? 'danger-quiet' : 'quiet'"
        :tooltip="tipOf(command.title, command.description)"
        :disable="runRowCommand.isPending.value"
        :data-testid="`grid-row-command-${command.name}-${row.id}`"
        @click="runCommand(command, row)"
      />
      <AppIconButton
        v-if="canOpenRecord"
        icon="table_rows"
        compact
        tooltip="Read this row downwards"
        :data-testid="`grid-open-row-${row.id}`"
        @click="openRecord(row)"
      />
    </template>

    <template #cell-overlay="{ row, column, value }">
      <!-- A corner mark rather than a button in the cell: a way out belongs to
           the value, and an icon the size of a button was drawn over the value
           it belongs to. `title=""` is not decoration — the cell carries the
           browser's own hint about editing, and without an empty one here that
           hint was drawn beside this tooltip whenever the mark was hovered. -->
      <button
        v-for="(reference, index) in cellReferences(column.id, value)"
        :key="reference.name"
        type="button"
        class="data-grid__follow"
        title=""
        :style="{ insetInlineEnd: `${index * 12}px` }"
        :disabled="jumping"
        :aria-label="`Go to ${reference.target_title}`"
        :data-testid="`grid-follow-${row.id}-${reference.name}`"
        @click.stop="follow(row.values, reference)"
        @dblclick.stop
      >
        <AppTooltip>Go to {{ reference.target_title }}</AppTooltip>
      </button>
      <!-- The opposite corner for the opposite direction: what points at this
           row. A menu rather than a jump, because there is usually more than
           one answer and only the reader knows which one they meant (D110). -->
      <button
        v-if="cellArriving(column.id, value).length > 0"
        type="button"
        class="data-grid__follow data-grid__follow--back"
        title=""
        :disabled="jumping"
        aria-label="What points at this row"
        :data-testid="`grid-arriving-${row.id}-${column.id}`"
        @click.stop
        @dblclick.stop
      >
        <AppTooltip>What points at this row</AppTooltip>
        <AppMenu
          :items="
            cellArriving(column.id, value).map((reference) => ({
              name: reference.name,
              label: reference.source_title,
            }))
          "
          @select="
            (name) =>
              followBack(
                row.values,
                cellArriving(column.id, value).find(
                  (reference) => reference.name === name
                )!
              )
          "
        />
      </button>
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
      <!-- One window per action, opened where the action was offered. The
           form, the preview and the refusals are the catalog's own; only the
           place it is asked from is new. -->
      <ActionDialog
        v-if="openAction !== null"
        :command="openAction"
        :connector-id="connectorId"
        :node-ids="[nodeId]"
        :node-label="title ?? nodeId"
        @update:command="openAction = $event"
        @done="actionDone"
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
        :column-count="downloadColumns.length"
        :filter-count="queryState.filters.length"
        :all-supported="result.export_supported === true"
        :all-reason="result.export_reason ?? undefined"
        :running="writingOut"
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
/* The mark itself is drawn by the corner triangle below; the button is a
   little larger than it so that pointing at it is not an aiming exercise. */
.data-grid__follow {
  position: absolute;
  inset-block-start: 0;
  inset-inline-end: 0;
  width: 12px;
  height: 12px;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  /* No layer of its own. It is content of one cell and has only to sit over
     that cell's value, which nothing positioned needs a z-index for — and
     with one it tied with the pinned column beside it, so the mark of a
     column scrolled underneath was drawn on top of the column that is
     supposed to hide it. */
}

.data-grid__follow::after {
  content: "";
  position: absolute;
  inset-block-start: 0;
  inset-inline-end: 0;
  border-block-start: 9px solid var(--dp-link);
  border-inline-start: 9px solid transparent;
}

.data-grid__follow:hover::after,
.data-grid__follow:focus-visible::after {
  border-block-start-width: 12px;
  border-inline-start-width: 12px;
}

.data-grid__follow:disabled {
  cursor: default;
}

.data-grid__follow:disabled::after {
  border-block-start-color: var(--dp-text-faint);
}

/* The way back, in the corner opposite the way out: same colour, because both
   mean "this row is related to rows elsewhere", and a different corner,
   because they lead in opposite directions (D110). */
.data-grid__follow--back {
  inset-block-start: auto;
  inset-block-end: 0;
}

.data-grid__follow--back::after {
  inset-block-start: auto;
  inset-block-end: 0;
  border-block-start: 0;
  border-block-end: 9px solid var(--dp-link);
  border-inline-start: 9px solid transparent;
}

.data-grid__follow--back:hover::after,
.data-grid__follow--back:focus-visible::after {
  border-block-start-width: 0;
  border-block-end-width: 12px;
  border-inline-start-width: 12px;
}

.data-grid__follow--back:disabled::after {
  border-block-end-color: var(--dp-text-faint);
}

.data-grid__insert-error {
  margin: var(--dp-space-2) var(--dp-space-3);
}
</style>
