<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { Sort } from "@/client"
import { t } from "@/shared/i18n"
import { AppBadge, AppCopyButton, AppIconButton, AppToolbarRule } from "@/shared/ui"

import FilterEditor from "./FilterEditor.vue"
import ColumnManager from "./ColumnManager.vue"
import SortEditor from "./SortEditor.vue"
import type { ColumnLayoutState } from "./columnLayout"
import type { TabularColumn } from "./tabular"
import { NOT_OFFERED, tipOf, TOOLBAR_GROUPS } from "./toolbar"
import type { Filter } from "./types"

const props = defineProps<{
  columns: TabularColumn[]
  filters: Filter[]
  sort: Sort[]
  layout: ColumnLayoutState
  canCopy?: boolean
}>()
const emit = defineEmits<{
  "update:filters": [value: Filter[]]
  "update:sort": [value: Sort[]]
  "update:layout": [value: ColumnLayoutState]
  copy: []
}>()
const filtersOpen = ref(false)
const sortOpen = ref(false)
const columnsOpen = ref(false)
const canFilter = computed(() =>
  props.columns.some((column) => (column.filter_operators?.length ?? 0) > 0)
)
const canSort = computed(() => props.columns.some((column) => column.sortable === true))
const hiddenColumns = computed(
  () => props.columns.filter((column) => props.layout.columnVisibility[column.id] === false).length
)

/**
 * The groups, their names and their order, in one place.
 *
 * Every one of them is always drawn. A command with nothing to say for itself
 * is greyed rather than dropped, so a group is never empty and the row never
 * changes shape between one source and another.
 */
const groups = TOOLBAR_GROUPS
</script>

<template>
  <div
    class="grid-header"
    data-testid="grid-header"
  >
    <div class="grid-header__bar dp-scroll-edges">
      <div
        v-for="(group, index) in groups"
        :key="group.name"
        class="grid-header__group"
        :data-testid="`grid-group-${group.name}`"
      >
        <!-- The line stands between two groups and belongs to neither, so the
             group on its right draws it rather than it having a place of its
             own to be forgotten in. -->
        <AppToolbarRule v-if="index > 0" />
        <div class="grid-header__group-body">
          <span class="grid-header__label">{{ group.label }}</span>
          <div class="grid-header__row">
            <template v-if="group.name === 'view'">
              <!-- A count on the button's corner, so an active query is
                   visible without opening the editor or hovering: a followed
                   reference lands as a filter the tab remembers. -->
              <AppIconButton
                :icon="appIcons.filterAlt"
                :tooltip="canFilter
                  ? (filters.length > 0 ? t('grid.header.filters_count', { n: filters.length }) : t('grid.header.filters'))
                  : tipOf(t('grid.header.filters'), NOT_OFFERED.filter)"
                :disable="!canFilter"
                data-testid="grid-filter"
                @click="filtersOpen = !filtersOpen"
              >
                <AppBadge
                  v-if="filters.length > 0"
                  corner
                  :label="String(filters.length)"
                  data-testid="grid-filter-count"
                />
              </AppIconButton>
              <AppIconButton
                :icon="appIcons.sort"
                :tooltip="canSort
                  ? (sort.length > 0 ? t('grid.header.sort_count', { n: sort.length }) : t('grid.header.sort'))
                  : tipOf(t('grid.header.sort'), NOT_OFFERED.sort)"
                :disable="!canSort"
                data-testid="grid-sort"
                @click="sortOpen = !sortOpen"
              >
                <AppBadge
                  v-if="sort.length > 0"
                  corner
                  :label="String(sort.length)"
                  data-testid="grid-sort-count"
                />
              </AppIconButton>
              <AppIconButton
                :icon="appIcons.viewColumn"
                :tooltip="hiddenColumns > 0 ? t('grid.header.columns_hidden', { n: hiddenColumns }) : t('grid.header.columns')"
                :disable="columns.length === 0"
                data-testid="grid-columns"
                @click="columnsOpen = !columnsOpen"
              >
                <AppBadge
                  v-if="hiddenColumns > 0"
                  corner
                  :label="String(hiddenColumns)"
                  data-testid="grid-columns-count"
                />
              </AppIconButton>
              <slot name="commands-view" />
            </template>
            <template v-else-if="group.name === 'open'">
              <slot name="commands-open" />
            </template>
            <template v-else-if="group.name === 'out'">
              <AppCopyButton
                :tooltip="t('grid.header.copy')"
                :disable="!canCopy"
                data-testid="grid-copy"
                @click="emit('copy')"
              />
              <slot name="commands-out" />
            </template>
            <template v-else-if="group.name === 'write'">
              <slot name="commands-write" />
            </template>
            <template v-else>
              <slot name="commands-tab" />
            </template>
          </div>
        </div>
      </div>
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

/* Scrolls sideways rather than wrapping or folding anything away: every
   command keeps the place it was given, and a narrow panel reaches the far
   ones by scrolling to them, with a shadow at the edge (`dp-scroll-edges`).
   A scroll comes to rest on a group's edge: resting anywhere cut a label in
   the middle of a word, which read as broken rather than out of view. */
.grid-header__bar {
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  padding: var(--dp-space-1);
}

.grid-header__group {
  display: flex;
  align-items: stretch;
  flex: none;
  scroll-snap-align: start;
}

.grid-header__group-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 0 var(--dp-space-half);
}

.grid-header__label {
  padding-inline-start: var(--dp-space-2);
  font-size: var(--dp-font-size);
  font-weight: 600;
  line-height: var(--dp-line-height);
  color: var(--dp-text);
  white-space: nowrap;
  user-select: none;
}

.grid-header__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
  white-space: nowrap;
}

/* The corner count is positioned against this, so an active query keeps its
   mark while the bar scrolls sideways. In flow it would widen the button and
   push its icon off the row's axis. */
</style>
