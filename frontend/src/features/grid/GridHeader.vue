<script setup lang="ts">
import { computed, ref } from "vue"

import type { FetchColumn } from "@/client"
import { AppButton, AppSelect, AppTooltip } from "@/shared/ui"

import FilterEditor from "./FilterEditor.vue"
import { PAGE_SIZES } from "./types"
import type { Filter, PageSize } from "./types"

const props = defineProps<{ pageSize: PageSize; columns: FetchColumn[]; filters: Filter[] }>()
const emit = defineEmits<{
  "update:pageSize": [value: PageSize]
  "update:filters": [value: Filter[]]
}>()
const pageSizeOptions = PAGE_SIZES.map((size) => ({ label: String(size), value: size }))
const filtersOpen = ref(false)
const canFilter = computed(() =>
  props.columns.some((column) => (column.filter_operators?.length ?? 0) > 0)
)

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
          :title="canFilter ? undefined : 'This source does not support filtering'"
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
        <AppButton
          label="Sort"
          variant="quiet"
          size="sm"
          disable
        />
        <AppButton
          label="Columns"
          variant="quiet"
          size="sm"
          disable
        />
        <AppButton
          label="Pin"
          variant="quiet"
          size="sm"
          disable
        />
        <AppButton
          label="Copy"
          variant="quiet"
          size="sm"
          disable
        />
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
