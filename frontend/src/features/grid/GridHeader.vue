<script setup lang="ts">
import { computed, ref } from "vue"

import type { FetchColumn, Sort } from "@/client"
import { AppCopyButton, AppIconButton, AppSelect } from "@/shared/ui"

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
  canCopy?: boolean
  canPaste?: boolean
  pasteSupported?: boolean
  canInsert?: boolean
  canImport?: boolean
  insertSupported?: boolean
  canDelete?: boolean
  deleteSupported?: boolean
  deleteCount?: number
  canDownload?: boolean
  downloading?: boolean
  canDescribe?: boolean
  canChart?: boolean
  canCreateTable?: boolean
}>()
const emit = defineEmits<{
  "update:pageSize": [value: PageSize]
  "update:filters": [value: Filter[]]
  "update:sort": [value: Sort[]]
  "update:layout": [value: ColumnLayoutState]
  copy: []
  paste: []
  insert: []
  bringIn: []
  delete: []
  download: []
  describe: []
  chart: []
  createTable: []
}>()
const pageSizeOptions = PAGE_SIZES.map((size) => ({ label: String(size), value: size }))
const filtersOpen = ref(false)
const sortOpen = ref(false)
const columnsOpen = ref(false)
const canFilter = computed(() =>
  props.columns.some((column) => (column.filter_operators?.length ?? 0) > 0)
)
const canSort = computed(() => props.columns.some((column) => column.sortable === true))

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
          v-if="canFilter"
          data-testid="grid-filter-command"
        >
          <AppIconButton
            icon="filter_alt"
            :tooltip="filters.length > 0 ? `Filters (${filters.length})` : 'Filters'"
            data-testid="grid-filter"
            @click="filtersOpen = !filtersOpen"
          />
        </span>
        <span
          v-if="canSort"
          data-testid="grid-sort-command"
        >
          <AppIconButton
            icon="sort"
            :tooltip="sort.length > 0 ? `Sort (${sort.length})` : 'Sort'"
            data-testid="grid-sort"
            @click="sortOpen = !sortOpen"
          />
        </span>
        <AppIconButton
          v-if="columns.length > 0"
          icon="view_column"
          tooltip="Columns"
          data-testid="grid-columns"
          @click="columnsOpen = !columnsOpen"
        />
        <AppCopyButton
          v-if="columns.length > 0"
          tooltip="Copy the selection"
          :disable="!canCopy"
          data-testid="grid-copy"
          @click="emit('copy')"
        />
        <AppIconButton
          v-if="canImport"
          icon="input"
          tooltip="Bring rows in"
          data-testid="grid-import"
          @click="emit('bringIn')"
        />
        <AppIconButton
          v-if="pasteSupported"
          icon="content_paste"
          tooltip="Paste into the selection"
          :disable="!canPaste"
          data-testid="grid-paste"
          @click="emit('paste')"
        />
        <AppIconButton
          v-if="canDownload"
          icon="download"
          tooltip="Download"
          :disable="!canDownload || downloading"
          :loading="downloading"
          data-testid="grid-download"
          @click="emit('download')"
        />
        <AppIconButton
          v-if="canChart"
          icon="insert_chart"
          tooltip="Charts"
          data-testid="grid-charts"
          @click="emit('chart')"
        />
        <AppIconButton
          v-if="canCreateTable"
          icon="post_add"
          tooltip="Create table from these rows"
          data-testid="grid-create-table"
          @click="emit('createTable')"
        />
        <AppIconButton
          v-if="canDescribe"
          icon="account_tree"
          tooltip="Structure"
          data-testid="grid-structure"
          @click="emit('describe')"
        />
        <span
          v-if="insertSupported"
          data-testid="grid-insert-command"
        >
          <AppIconButton
            icon="add"
            tooltip="Insert row"
            :disable="!canInsert"
            data-testid="grid-insert"
            @click="emit('insert')"
          />
        </span>
        <span
          v-if="deleteSupported"
          data-testid="grid-delete-command"
        >
          <AppIconButton
            icon="remove"
            :tooltip="deleteCount ? `Delete ${deleteCount} selected rows` : 'Delete selected rows'"
            :disable="!canDelete"
            data-testid="grid-delete"
            @click="emit('delete')"
          />
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
