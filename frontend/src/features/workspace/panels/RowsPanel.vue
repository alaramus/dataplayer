<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from "vue"

import type { FetchRequest, NodeRepresentation, ReferencedRows, RowsView } from "@/client"
import DataGrid from "@/features/grid/DataGrid.vue"
import type { Filter } from "@/features/grid/types"
import { emptyDraft, writeDraft } from "@/features/queries/draft"
import { useGenerateQuery, useQueryProfile } from "@/features/queries/runs"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { useSiblingTables } from "@/features/catalog/api"
import { messageOf } from "@/shared/api/errors"
import type { Freshness } from "@/shared/freshness/freshness"
import { useToast } from "@/shared/ui"

/**
 * One relation, in its own tab.
 *
 * The row estimate is not passed on: it belongs to the catalog node, and a
 * panel restored from storage has not read the catalog. The grid pages by
 * has_more when it has no estimate, which is what a file source gives it too.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  describable: boolean
  representations?: NodeRepresentation[]
  /** The node whose children are this one's sibling tables, when it has one. */
  containerId?: string
}>()
const workspace = useWorkspaceActions()

const contentRepresentation = computed(() =>
  props.representations?.find((representation) => representation.kind !== "table")
)

/**
 * The other tables this one is one of: the sheets of a workbook, asked for
 * through the same cached query the catalog uses, so switching between them
 * reads the file once.
 *
 * The node this tab is on is one of them — a workbook opens as its first
 * sheet, so the tab is on the file itself until somebody switches.
 */
const sheets = useSiblingTables(
  computed(() => props.connectorId),
  computed(() => props.containerId ?? null)
)
/** Which one is being read: the one this tab is on, or the first — a workbook
    opens as its first sheet, so the tab that opened is on the file itself. */
const currentSheet = computed(
  () =>
    sheets.value.find((sheet) => sheet.id === props.nodeId) ??
    sheets.value[0] ??
    null
)

/**
 * Switch this tab to another sheet, in place.
 *
 * The tab keeps its position, its place in the strip and its name: it is a tab
 * on the file, and which sheet of it is being read is said by the strip along
 * the foot. Renaming the tab to the sheet made the file disappear from the
 * screen the moment somebody looked at its second table.
 */
function showSheet(value: string) {
  const chosen = sheets.value.find((sheet) => sheet.id === value)
  if (chosen === undefined || chosen.id === props.nodeId) return
  workspace.showInPlace(props.panelId, {
    connectorId: props.connectorId,
    nodeId: chosen.id,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    // The sheet's own answers, not the workbook's: a sheet states its columns
    // and can be described, and the file it lives in cannot.
    describable: chosen.describable === true,
    representations: chosen.representations,
    containerId: props.containerId,
  })
}

const grid = useTemplateRef<{
  reload: () => Promise<void>
  freshness: Freshness | undefined
  cacheWindow: number | null | undefined
}>("grid")

/**
 * How old the page on screen is, taken from the grid that read it.
 *
 * The grid owns the query — which page, which filters — so it owns the answer
 * about freshness; the row of commands belongs to the tab. Read through the
 * grid's exposed values rather than asked for a second time, because a second
 * read would be a second cache to fall out of step with the first (D7).
 */
const freshness = computed(() => grid.value?.freshness)
const cacheWindow = computed(() => grid.value?.cacheWindow)

/**
 * Whether this source writes SQL about its own nodes.
 *
 * Asked of the source rather than derived from its type: a screen never
 * branches on which adapter it is talking to (D62).
 */
const profile = useQueryProfile(() => props.connectorId)
const canQuery = computed(() => profile.data.value?.supports_generated_query === true)
const generate = useGenerateQuery()
const toast = useToast()

/**
 * Open a console on this relation, with a bounded SELECT the source wrote.
 *
 * The statement comes from the server because quoting a name belongs to the
 * dialect; this panel only says which node it is about (D65).
 */
async function openAsQuery() {
  try {
    const generated = await generate.mutateAsync({
      connectorId: props.connectorId,
      body: { node_id: props.nodeId, kind: "select" },
    })
    // Nothing is put in the library: pressing this used to leave a document
    // behind every time, so a person who looked at six tables had six queries
    // they never wrote. The console holds the text until they keep it (D65).
    const draftId = crypto.randomUUID()
    writeDraft(draftId, { ...emptyDraft(props.title), body: generated.text })
    workspace.openQueryDraft({
      draftId,
      connectorId: props.connectorId,
      connectorName: props.connectorName,
      title: props.title,
    })
  } catch (cause) {
    toast.error(messageOf(cause, "Could not open this table as a query"))
  }
}

useReloadable(() => props.panelId, async () => {
  await grid.value?.reload()
})

/**
 * The predicate this tab was navigated to by, once.
 *
 * Watched rather than received as a prop of the panel: the workspace binds a
 * panel's props when the panel is first drawn and keeps that binding, so a
 * tab already open would never see a second arrival. Taken from the workspace
 * for the same reason `revealTarget` is — see the note there.
 */
const referenceFilters = ref<Filter[] | null>(null)

watch(
  workspace.followTarget,
  () => {
    const taken = workspace.takeFollow(props.connectorId, props.nodeId)
    if (taken !== null) referenceFilters.value = [...taken.filters]
  },
  { immediate: true }
)

/**
 * The view a link asked this tab to show, once.
 *
 * Taken the same way a followed predicate is, and for the same reason: this
 * tab may have been open already, and a panel's props are bound when it is
 * first drawn. See D60.
 */
const sharedView = ref<RowsView | null>(null)

watch(
  workspace.sharedTarget,
  () => {
    const taken = workspace.takeShared(props.connectorId, props.nodeId)
    if (taken !== null) sharedView.value = taken.view
  },
  { immediate: true }
)

/**
 * What this tab is actually showing, which is not always the node it is on.
 *
 * A workbook opens as its first sheet, so a tab opened on the file is reading
 * a sheet — and everything it offers about what it shows has to be that
 * sheet's. The structure button was the file's answer, and a file that holds
 * tables states no columns of its own: the button appeared only once somebody
 * had switched sheets, which is the moment the node stopped being the file.
 */
const showing = computed(() => currentSheet.value)
const canDescribe = computed(() =>
  showing.value === null ? props.describable : showing.value.describable === true
)

function showStructure() {
  const node = showing.value
  workspace.openStructure({
    connectorId: props.connectorId,
    nodeId: node?.id ?? props.nodeId,
    // Named after the sheet where there is one: this tab is called after the
    // file and shows whichever sheet is chosen, but the structure is one
    // sheet's columns and a tab of them called after the file would be three
    // tabs with one name.
    title: node?.name ?? props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
  })
}

function showContent() {
  const representation = contentRepresentation.value
  if (representation === undefined) return
  const others = (props.representations ?? []).filter(
    (candidate) => candidate.kind !== representation.kind
  )
  workspace.openRepresentation({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    representations: [representation, ...others],
    describable: props.describable,
  })
}

function showChart(request: FetchRequest, columns: string[]) {
  workspace.openChart({
    connectorId: props.connectorId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    request,
    columns,
  })
}

/** One row of this relation, read downwards in a panel of its own (D111). */
function showRecord(value: { request: FetchRequest; index: number }) {
  workspace.openRecord({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    describable: canDescribe.value,
    request: value.request,
    index: value.index,
  })
}

function showReferenced(target: ReferencedRows) {
  workspace.followReference({
    connectorId: props.connectorId,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    target,
  })
}
</script>

<template>
  <div class="rows-panel">
    <DataGrid
      ref="grid"
      :connector-id="connectorId"
      :node-id="nodeId"
      :title="title"
      :can-describe="canDescribe"
      :can-query="canQuery"
      :content-title="contentRepresentation?.title"
      :reference-filters="referenceFilters"
      :shared-view="sharedView"
      @query="openAsQuery"
      @describe="showStructure"
      @content="showContent"
      @chart="showChart"
      @follow="showReferenced"
      @record="showRecord"
    >
      <template #commands-end>
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
          :freshness="freshness"
          :cache-ttl-seconds="cacheWindow"
        />
      </template>

      <!-- On the row the pager is on, at the other end of it: which sheet is
           being read is about the whole page, the way the page number is.
           Only where there is a choice — one sheet is a table, and a strip of
           one tab is a control that does nothing (D51). -->
      <template
        v-if="sheets.length > 1"
        #pager-start
      >
        <div
          class="rows-panel__sheets"
          role="tablist"
          data-testid="sheet-switcher"
        >
          <button
            v-for="sheet in sheets"
            :key="sheet.id"
            type="button"
            role="tab"
            class="rows-panel__sheet"
            :class="{ 'rows-panel__sheet--here': sheet.id === currentSheet?.id }"
            :aria-selected="sheet.id === currentSheet?.id"
            :data-testid="`sheet-${sheet.name}`"
            @click="showSheet(sheet.id)"
          >
            {{ sheet.name }}
          </button>
        </div>
      </template>
    </DataGrid>
  </div>
</template>

<style scoped>
/* A box of the height the section gave it: the grid keeps its own header and
   its pager still and scrolls the rows between them. See the spec, S10. */
.rows-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
/* The grid's scroller is the kit's .dp-panel-scroll, reached into because
   the grid keeps its commands and pager in the same box. */
.rows-panel :deep(.data-grid__scroll) {
  margin-right: calc(-1 * var(--dp-space-1));
}
/* Where a spreadsheet puts them: along the foot, beside the paging controls
   rather than above the columns, which belong to the sheet being read. */
.rows-panel__sheets {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
  min-width: 0;
  overflow-x: auto;
}
.rows-panel__sheet {
  flex: none;
  max-width: 180px;
  overflow: hidden;
  padding: var(--dp-space-half) var(--dp-space-2);
  border: none;
  border-radius: var(--dp-radius-control) var(--dp-radius-control) 0 0;
  background: none;
  color: var(--dp-text-muted);
  font: inherit;
  font-size: var(--dp-font-size-sm);
  white-space: nowrap;
  text-overflow: ellipsis;
  cursor: pointer;
}
.rows-panel__sheet:hover:not(.rows-panel__sheet--here) {
  background: var(--dp-hover);
}
/* The one being read, marked the way a current tab is (D186): the tab
   ground and 500, not the blue of a ticked row and a line under it. */
.rows-panel__sheet--here {
  background: var(--dp-tab-current);
  color: var(--dp-text);
  font-weight: 500;
}
</style>
