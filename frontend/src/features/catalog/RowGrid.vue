<script setup lang="ts">
import { ref, watch } from "vue"

import type { FetchResult, Sort } from "@/client"
import { useFetchRows } from "@/features/catalog/api"
import { displayValue, toGridColumns, toGridRows } from "@/features/catalog/rows"
import type { GridColumn } from "@/features/catalog/rows"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppIconButton, AppTable } from "@/shared/ui"

const props = defineProps<{
  connectorId: string
  nodeId: string
  /** Approximate row count from the catalog node, when it has one. */
  rowEstimate?: number | null
}>()

/**
 * How this grid is re-read, for whoever holds it.
 *
 * The page and the order stay: the button says "read this again", not "start
 * over". Exposed rather than registered here because the grid does not know
 * which panel it is in — the panel does.
 */
defineExpose({ reload: () => load() })

const PAGE_SIZE = 50

const fetchRows = useFetchRows()

const columns = ref<GridColumn[]>([])
const rows = ref<Record<string, unknown>[]>([])
const page = ref(0)
const hasMore = ref(false)
// What the source said it can do in its last answer. A file has no index to
// order by, so the header must stop inviting a click the server will refuse.
const sortable = ref(true)
const sort = ref<Sort[]>([])
const error = ref("")

async function load() {
  error.value = ""
  try {
    const result: FetchResult = await fetchRows.mutateAsync({
      connectorId: props.connectorId,
      request: {
        node_id: props.nodeId,
        limit: PAGE_SIZE,
        offset: page.value * PAGE_SIZE,
        sort: sort.value,
        filters: [],
      },
    })
    columns.value = toGridColumns(result)
    rows.value = toGridRows(result)
    hasMore.value = result.has_more
    sortable.value = result.columns.some((column) => column.sortable === true)
  } catch (cause) {
    error.value = messageOf(cause, "Could not read the rows")
    columns.value = []
    rows.value = []
    hasMore.value = false
  }
}

function sortBy(column: string) {
  if (!sortable.value) return
  const current = sort.value[0]
  sort.value =
    current && current.column === column && !current.descending
      ? [{ column, descending: true }]
      : [{ column, descending: false }]
  page.value = 0
  void load()
}

function turnPage(delta: number) {
  page.value = Math.max(0, page.value + delta)
  void load()
}

watch(
  () => [props.connectorId, props.nodeId],
  () => {
    page.value = 0
    sort.value = []
    void load()
  },
  { immediate: true }
)
</script>

<template>
  <div
    class="row-grid"
    data-testid="row-grid"
  >
    <AppBanner
      v-if="error"
      tone="error"
      class="q-mb-md"
      data-testid="grid-error"
    >
      {{ error }}
    </AppBanner>

    <AppTable
      v-else
      class="row-grid__table"
      :rows="rows"
      :columns="columns"
      :loading="fetchRows.isPending.value"
      row-key="__index"
      compact
      sticky
      :paged="false"
      empty-text="No rows"
    >
      <template #header-cell="cellProps">
        <q-th
          :props="cellProps"
          :class="{ 'cursor-pointer': sortable }"
          @click="sortBy(cellProps.col.name)"
        >
          {{ cellProps.col.label }}
          <q-icon
            v-if="sort[0]?.column === cellProps.col.name"
            :name="sort[0]?.descending ? 'arrow_downward' : 'arrow_upward'"
            size="14px"
          />
        </q-th>
      </template>

      <template #body-cell="cellProps">
        <q-td :props="cellProps">
          <span :class="{ 'text-grey': cellProps.value === null }">
            {{ displayValue(cellProps.value) }}
          </span>
        </q-td>
      </template>
    </AppTable>

    <div class="row-grid__pager row items-center justify-end q-gutter-sm q-mt-sm">
      <div class="text-caption text-grey">
        Rows {{ page * PAGE_SIZE + 1 }}–{{ page * PAGE_SIZE + rows.length }}
        <template v-if="rowEstimate !== null && rowEstimate !== undefined">
          of ~{{ rowEstimate }}
        </template>
      </div>
      <AppIconButton
        icon="chevron_left"
        tooltip="Previous page"
        :disable="page === 0"
        data-testid="grid-prev"
        @click="turnPage(-1)"
      />
      <AppIconButton
        icon="chevron_right"
        tooltip="Next page"
        :disable="!hasMore"
        data-testid="grid-next"
        @click="turnPage(1)"
      />
    </div>
  </div>
</template>

<style scoped>
.row-grid {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.row-grid__table {
  flex: 1;
  min-height: 0;
}
.row-grid__pager {
  flex: none;
}
</style>
