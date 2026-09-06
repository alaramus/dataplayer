<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { FetchColumn, ResultColumn, Sort } from "@/client"
import ChartView from "@/features/charts/ChartView.vue"
import TabularGrid from "@/features/grid/TabularGrid.vue"
import { defaultColumnLayout } from "@/features/grid/columnLayout"
import type { ColumnLayoutState } from "@/features/grid/columnLayout"
import { saveBrowserDownload, filenameFromDisposition } from "@/features/grid/download"
import type { TabularColumn } from "@/features/grid/tabular"
import type { Filter, GridRow, PageSize } from "@/features/grid/types"
import { useDownloadResult, useResultPage } from "@/features/queries/runs"
import { messageOf } from "@/shared/api/errors"
import { AppIconButton, useToast } from "@/shared/ui"

/**
 * One captured result, read as a table (D64).
 *
 * The controlled tabular surface of D24 with a different controller behind it:
 * a query result has no update, insert, delete, reference, structure or import
 * command, because an arbitrary projection has no row identity to act on. What
 * it does have is paging, filtering and ordering — over the snapshot, which
 * the empty state and the download both say.
 */

const props = withDefaults(
  defineProps<{
    resultId: string
    title?: string
    /** Whether this result came from the run before the one now going. */
    stale?: boolean
  }>(),
  { title: "result", stale: false }
)

const toast = useToast()
const charting = ref(false)
const page = ref(0)
const pageSize = ref<PageSize>(100)
const filters = ref<Filter[]>([])
const sort = ref<Sort[]>([])
const layout = ref<ColumnLayoutState | null>(null)

const request = computed(() => ({
  view: { filters: filters.value, sort: sort.value },
  offset: page.value * pageSize.value,
  limit: pageSize.value,
}))
const snapshot = useResultPage(() => props.resultId, request)
const download = useDownloadResult()

defineExpose({ reload: async () => void (await snapshot.refetch()) })

const columns = computed<TabularColumn[]>(() =>
  (snapshot.data.value?.columns ?? []).map(tabularColumnOf)
)
const rows = computed<GridRow[]>(() =>
  (snapshot.data.value?.rows ?? []).map((values, index) => ({
    id: String(page.value * pageSize.value + index),
    values,
  }))
)
const total = computed(() => snapshot.data.value?.total_rows ?? 0)
const hasMore = computed(() => (page.value + 1) * pageSize.value < total.value)
const error = computed(() =>
  snapshot.isError.value
    ? messageOf(snapshot.error.value, "This result is no longer available")
    : ""
)

/**
 * Every operator, because filtering happens over rows already read.
 *
 * A relation's column offers what its source can do with it; a snapshot's
 * offers what this application can do with text it is holding.
 */
function tabularColumnOf(column: ResultColumn): TabularColumn {
  return {
    id: column.id,
    label: column.name,
    type: column.type,
    sortable: true,
    filter_operators: [
      "eq",
      "ne",
      "gt",
      "gte",
      "lt",
      "lte",
      "contains",
      "starts_with",
      "in",
      "is_null",
      "is_not_null",
    ],
  }
}

// A layout belongs to the shape of the result: reconciled by its positional
// ids, so a second run of the same query keeps the columns where they were.
// Declared before the watcher, which runs immediately and would otherwise
// read it before it exists.
let layoutSignature = ""
watch(
  columns,
  (found) => {
    const signature = found.map((column) => column.id).join(" ")
    if (layout.value === null || layoutSignature !== signature) {
      layoutSignature = signature
      layout.value = defaultColumnLayout(found)
    }
  },
  { immediate: true }
)

function turnPage(delta: -1 | 1) {
  page.value = Math.max(0, page.value + delta)
}

function changePageSize(size: PageSize) {
  pageSize.value = size
  page.value = 0
}

function changeFilters(next: Filter[]) {
  filters.value = next
  page.value = 0
}

function changeSort(next: Sort[]) {
  sort.value = next
  page.value = 0
}

/**
 * The page as a chart, over exactly the rows on screen (D35, D65).
 *
 * The same bounded chart the grid has: a chart of a snapshot page is the page,
 * not a second question asked of the source. A whole-result aggregate is a
 * later operation of its own.
 */
const chartColumns = computed<FetchColumn[]>(() =>
  (snapshot.data.value?.columns ?? []).map((column) => ({
    name: column.name,
    type: column.type,
  }))
)
const chartRows = computed(() => snapshot.data.value?.rows ?? [])

async function save(scope: "page" | "all") {
  try {
    const saved = await download.mutateAsync({
      resultId: props.resultId,
      body: {
        scope,
        title: props.title,
        view: { filters: filters.value, sort: sort.value },
        offset: page.value * pageSize.value,
        limit: pageSize.value,
      },
    })
    saveBrowserDownload(
      saved.blob,
      filenameFromDisposition(saved.disposition ?? "", `${props.title}.csv`)
    )
    toast.success(
      scope === "all"
        ? "Every captured row saved to your Downloads folder"
        : "This page saved to your Downloads folder"
    )
  } catch (cause) {
    toast.error(messageOf(cause, "Could not save this result"))
  }
}
</script>

<template>
  <div
    v-if="charting"
    class="result-table__chart"
  >
    <div class="result-table__chart-bar">
      <span class="result-table__note">
        This page · rows {{ page * pageSize + 1 }}–{{ page * pageSize + chartRows.length }}
        of {{ total }} captured
      </span>
      <AppIconButton
        icon="table_rows"
        tooltip="Back to the rows"
        data-testid="result-chart-close"
        @click="charting = false"
      />
      <slot name="commands-end" />
    </div>
    <ChartView
      :view-key="`result:${resultId}`"
      :columns="chartColumns"
      :rows="chartRows"
      :offset="page * pageSize"
      class="result-table__chart-body"
    />
  </div>
  <TabularGrid
    v-else-if="layout !== null"
    :columns="columns"
    :rows="rows"
    :page="page"
    :page-size="pageSize"
    :filters="filters"
    :sort="sort"
    :layout="layout"
    :has-more="hasMore"
    :loading="snapshot.isPending.value"
    :refreshing="snapshot.isFetching.value && snapshot.data.value !== undefined"
    :error="error"
    :show-reset="false"
    empty-text="No rows in this result"
    @update:page-size="changePageSize"
    @update:filters="changeFilters"
    @update:sort="changeSort"
    @update:layout="layout = $event"
    @turn-page="turnPage"
    @retry="snapshot.refetch()"
  >
    <template #commands-open>
      <AppIconButton
        icon="insert_chart"
        tooltip="Chart this page"
        data-testid="result-chart"
        @click="charting = true"
      />
    </template>

    <template #commands-out>
      <AppIconButton
        icon="download"
        tooltip="Save this page"
        :disable="download.isPending.value"
        data-testid="result-download-page"
        @click="save('page')"
      />
      <AppIconButton
        icon="download_for_offline"
        tooltip="Save every captured row"
        :disable="download.isPending.value"
        data-testid="result-download-all"
        @click="save('all')"
      />
    </template>

    <template #commands-tab>
      <slot name="commands-end" />
    </template>

    <!-- Beside the range rather than among the commands: neither of these is
         something to press, and both are about how much of the result is
         being looked at. -->
    <template #pager-start>
      <span
        v-if="stale"
        class="result-table__stale"
        data-testid="result-previous"
      >Previous result</span>
      <span
        v-if="snapshot.data.value?.truncated"
        class="result-table__truncated"
        data-testid="result-truncated"
      >Capped at {{ total }} rows</span>
    </template>
  </TabularGrid>
</template>

<style scoped>
.result-table__chart {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.result-table__chart-bar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 4px;
  border-bottom: 1px solid var(--dp-border-faint);
}
.result-table__chart-body {
  flex: 1;
  min-height: 0;
}
.result-table__note {
  padding-inline: 6px;
  color: var(--dp-text-muted);
  font-size: 11px;
}
.result-table__stale,
.result-table__truncated {
  align-self: center;
  padding-inline: 6px;
  color: var(--dp-text-muted);
  font-size: 11px;
  white-space: nowrap;
}
.result-table__stale {
  color: var(--dp-callout-caution);
}
</style>
