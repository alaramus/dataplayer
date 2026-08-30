<script setup lang="ts">
import { computed, ref } from "vue"

import type { FetchColumn, Sort } from "@/client"
import { AppButton, AppCopyButton, AppSelect, AppTooltip } from "@/shared/ui"

import FilterEditor from "./FilterEditor.vue"
import ColumnManager from "./ColumnManager.vue"
import SortEditor from "./SortEditor.vue"
import type { ColumnLayoutState } from "./columnLayout"
import { PAGE_SIZES } from "./types"
import type { Filter, PageSize } from "./types"

const props = defineProps<{
  pageSize: PageSize
  columns: FetchColumn[]
  filters: Filter[]
  sort: Sort[]
  layout: ColumnLayoutState
  selectedColumn: string | null
  canCopy?: boolean
  canInsert?: boolean
  insertReason?: string
  canDelete?: boolean
  deleteReason?: string
  deleteCount?: number
  canDownload?: boolean
  downloading?: boolean
  canDescribe?: boolean
  canChart?: boolean
}>()
const emit = defineEmits<{
  "update:pageSize": [value: PageSize]
  "update:filters": [value: Filter[]]
  "update:sort": [value: Sort[]]
  "update:layout": [value: ColumnLayoutState]
  copy: []
  insert: []
  delete: []
  download: []
  describe: []
  chart: []
}>()
const pageSizeOptions = PAGE_SIZES.map((size) => ({ label: String(size), value: size }))
const filtersOpen = ref(false)
const sortOpen = ref(false)
const columnsOpen = ref(false)
const canFilter = computed(() =>
  props.columns.some((column) => (column.filter_operators?.length ?? 0) > 0)
)
const canSort = computed(() => props.columns.some((column) => column.sortable === true))

function toggleSelectedPin() {
  if (props.selectedColumn === null) return
  const pinnedLeft = props.layout.pinnedLeft.includes(props.selectedColumn)
    ? props.layout.pinnedLeft.filter((name) => name !== props.selectedColumn)
    : [...props.layout.pinnedLeft, props.selectedColumn]
  emit("update:layout", { ...props.layout, pinnedLeft })
}

function selectPageSize(value: unknown) {
  if (typeof value === "number" && PAGE_SIZES.some((size) => size === value)) {
    emit("update:pageSize", value as PageSize)
  }
}
</script>

<template>
  <div
    class="grid-header"
    data-testid="grid-header"
  >
    <div class="grid-header__bar">
      <div class="grid-header__commands">
        <span
          data-testid="grid-filter-command"
        >
          <AppButton
            :label="filters.length > 0 ? `Filters (${filters.length})` : 'Filters'"
            variant="quiet"
            size="sm"
            :disable="!canFilter"
            data-testid="grid-filter"
            @click="filtersOpen = !filtersOpen"
          />
          <AppTooltip v-if="!canFilter">This source does not support filtering</AppTooltip>
        </span>
        <span
          data-testid="grid-sort-command"
        >
          <AppButton
            :label="sort.length > 0 ? `Sort (${sort.length})` : 'Sort'"
            variant="quiet"
            size="sm"
            :disable="!canSort"
            data-testid="grid-sort"
            @click="sortOpen = !sortOpen"
          />
          <AppTooltip v-if="!canSort">This source does not support sorting</AppTooltip>
        </span>
        <AppButton
          label="Columns"
          variant="quiet"
          size="sm"
          :disable="columns.length === 0"
          data-testid="grid-columns"
          @click="columnsOpen = !columnsOpen"
        />
        <AppButton
          :label="selectedColumn !== null && layout.pinnedLeft.includes(selectedColumn) ? 'Unpin' : 'Pin'"
          variant="quiet"
          size="sm"
          :disable="selectedColumn === null"
          :data-testid="selectedColumn === null ? 'grid-pin-current' : `grid-pin-${selectedColumn}`"
          @click="toggleSelectedPin"
        />
        <AppCopyButton
          tooltip="Copy the selection"
          :disable="!canCopy"
          data-testid="grid-copy"
          @click="emit('copy')"
        />
        <AppButton
          label="Download"
          icon="download"
          variant="quiet"
          size="sm"
          :disable="!canDownload || downloading"
          :loading="downloading"
          data-testid="grid-download"
          @click="emit('download')"
        />
        <AppButton
          label="Charts"
          icon="insert_chart"
          variant="quiet"
          size="sm"
          :disable="!canChart"
          data-testid="grid-charts"
          @click="emit('chart')"
        />
        <AppButton
          v-if="canDescribe"
          label="Structure"
          icon="account_tree"
          variant="quiet"
          size="sm"
          data-testid="grid-structure"
          @click="emit('describe')"
        />
        <span data-testid="grid-insert-command">
          <AppButton
            label="Insert"
            variant="quiet"
            size="sm"
            :disable="!canInsert"
            data-testid="grid-insert"
            @click="emit('insert')"
          />
          <AppTooltip v-if="!canInsert && insertReason">{{ insertReason }}</AppTooltip>
        </span>
        <span data-testid="grid-delete-command">
          <AppButton
            :label="deleteCount ? `Delete (${deleteCount})` : 'Delete'"
            variant="quiet"
            size="sm"
            :disable="!canDelete"
            data-testid="grid-delete"
            @click="emit('delete')"
          />
          <AppTooltip v-if="!canDelete && deleteReason">{{ deleteReason }}</AppTooltip>
        </span>
      </div>

      <AppSelect
        :model-value="pageSize"
        :options="pageSizeOptions"
        label="Rows"
        compact
        class="grid-header__page-size"
        data-testid="grid-page-size"
        @update:model-value="selectPageSize"
      />
    </div>

    <FilterEditor
      v-if="filtersOpen && canFilter"
      :columns="columns"
      :filters="filters"
      @apply="emit('update:filters', $event)"
      @close="filtersOpen = false"
    />
    <SortEditor
      v-if="sortOpen && canSort"
      :columns="columns"
      :sort="sort"
      @apply="emit('update:sort', $event)"
      @close="sortOpen = false"
    />
    <ColumnManager
      v-if="columnsOpen && columns.length > 0"
      :columns="columns"
      :layout="layout"
      @update:layout="emit('update:layout', $event)"
      @close="columnsOpen = false"
    />
  </div>
</template>

<style scoped>
.grid-header {
  display: flex;
  flex-direction: column;
  flex: none;
  border-bottom: 1px solid var(--dp-border);
}

.grid-header__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
  gap: 8px;
  overflow-x: auto;
}

.grid-header__commands {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.grid-header__page-size {
  width: 88px;
  flex: none;
}
</style>
