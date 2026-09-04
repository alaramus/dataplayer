<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from "vue"

import type { FetchRequest, NodeRepresentation, ReferencedRows, RowsView } from "@/client"
import DataGrid from "@/features/grid/DataGrid.vue"
import type { Filter } from "@/features/grid/types"
import { useCreateQueryDocument } from "@/features/queries/api"
import { useGenerateQuery, useQueryProfile } from "@/features/queries/runs"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { useSiblingTables } from "@/features/catalog/api"
import { messageOf } from "@/shared/api/errors"
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
 * The other tables this one is one of: the sheets of a workbook.
 *
 * A spreadsheet is one file with several tables in it, and being sent back to
 * the catalog to walk into a file to reach the second of them is what made it
 * feel like a folder. The container's children are asked for through the same
 * cached query the catalog uses, so opening a workbook and switching between
 * its sheets reads it once.
 *
 * The node this tab is on is one of them — a workbook opens as its first
 * sheet, so the tab that opened is on the file itself until somebody switches.
 */
const sheets = useSiblingTables(
  computed(() => props.connectorId),
  computed(() => props.containerId ?? null)
)
/** Which one is being read: the one this tab is on, or the first — a workbook
    opens as its first sheet, so the tab that opened is on the file itself. */
const currentSheet = computed(
  () =>
    sheets.value.find((sheet) => sheet.id === props.nodeId)?.id ??
    sheets.value[0]?.id ??
    ""
)

/**
 * Switch this tab to another sheet, in place.
 *
 * The same move a rename makes: the tab keeps its position and its place in
 * the strip, and its title becomes the sheet's. A second tab per sheet would
 * turn "look at the other one" into housekeeping.
 */
function showSheet(value: string) {
  const chosen = sheets.value.find((sheet) => sheet.id === value)
  if (chosen === undefined || chosen.id === props.nodeId) return
  workspace.showInPlace(props.panelId, {
    connectorId: props.connectorId,
    nodeId: chosen.id,
    title: chosen.name,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    // The sheet's own answers, not the workbook's: a sheet states its columns
    // and can be described, and the file it lives in cannot.
    describable: chosen.describable === true,
    representations: chosen.representations,
    containerId: props.containerId,
  })
}

const grid = useTemplateRef<{ reload: () => Promise<void> }>("grid")

/**
 * Whether this source writes SQL about its own nodes.
 *
 * Asked of the source rather than derived from its type: a screen never
 * branches on which adapter it is talking to (D62).
 */
const profile = useQueryProfile(() => props.connectorId)
const canQuery = computed(() => profile.data.value?.supports_generated_query === true)
const generate = useGenerateQuery()
const createDocument = useCreateQueryDocument()
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
    const document = await createDocument.mutateAsync({
      connector_id: props.connectorId,
      title: props.title,
      body: generated.text,
    })
    workspace.openQueryDocument({
      documentId: document.id,
      title: document.title,
      connectorName: document.connector_label,
    })
  } catch (cause) {
    toast.error(messageOf(cause, "Could not open this table as a query"))
  }
}

useReloadable(props.panelId, async () => {
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

function showStructure() {
  workspace.openStructure({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
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
      :can-describe="describable"
      :can-query="canQuery"
      :content-title="contentRepresentation?.title"
      :reference-filters="referenceFilters"
      :shared-view="sharedView"
      @query="openAsQuery"
      @describe="showStructure"
      @content="showContent"
      @chart="showChart"
      @follow="showReferenced"
    >
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
            :class="{ 'rows-panel__sheet--here': sheet.id === currentSheet }"
            :aria-selected="sheet.id === currentSheet"
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
  padding: 4px;
}
/* Where a spreadsheet puts them: along the foot, beside the paging controls
   rather than above the columns, which belong to the sheet being read. */
.rows-panel__sheets {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  overflow-x: auto;
}
.rows-panel__sheet {
  flex: none;
  max-width: 180px;
  overflow: hidden;
  padding: 3px 10px;
  border: none;
  border-radius: var(--dp-radius-control) var(--dp-radius-control) 0 0;
  background: none;
  color: var(--dp-text-muted);
  font: inherit;
  font-size: 12px;
  white-space: nowrap;
  text-overflow: ellipsis;
  cursor: pointer;
}
.rows-panel__sheet:hover:not(.rows-panel__sheet--here) {
  background: var(--dp-hover);
}
/* The one being read, marked the way the tab strip above marks a tab: a
   ground it keeps and a line under it. */
.rows-panel__sheet--here {
  background: var(--dp-selected);
  color: var(--dp-text-strong);
  box-shadow: inset 0 -2px 0 var(--dp-link);
}
</style>
