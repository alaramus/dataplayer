<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { Sort } from "@/client"
import { AppCopyButton, AppIconButton, AppToolbarRule } from "@/shared/ui"

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
    <div class="grid-header__bar">
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
              <span data-testid="grid-filter-command">
                <AppIconButton
                  :icon="appIcons.filterAlt"
                  :tooltip="canFilter
                    ? (filters.length > 0 ? `Filters (${filters.length})` : 'Filters')
                    : tipOf('Filters', NOT_OFFERED.filter)"
                  :disable="!canFilter"
                  data-testid="grid-filter"
                  @click="filtersOpen = !filtersOpen"
                />
              </span>
              <span data-testid="grid-sort-command">
                <AppIconButton
                  :icon="appIcons.sort"
                  :tooltip="canSort
                    ? (sort.length > 0 ? `Sort (${sort.length})` : 'Sort')
                    : tipOf('Sort', NOT_OFFERED.sort)"
                  :disable="!canSort"
                  data-testid="grid-sort"
                  @click="sortOpen = !sortOpen"
                />
              </span>
              <AppIconButton
                :icon="appIcons.viewColumn"
                tooltip="Columns"
                :disable="columns.length === 0"
                data-testid="grid-columns"
                @click="columnsOpen = !columnsOpen"
              />
              <slot name="commands-view" />
            </template>
            <template v-else-if="group.name === 'open'">
              <slot name="commands-open" />
            </template>
            <template v-else-if="group.name === 'out'">
              <AppCopyButton
                tooltip="Copy the selection"
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
   ones by scrolling to them.

   A shadow stands at an edge while there is more beyond it: cut off with no
   sign, the last group looked broken rather than out of view. The covers
   scroll with the content and hide each shadow when its end is reached; the
   shadows stay with the box. */
.grid-header__bar {
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  padding: var(--dp-space-1);
  background:
    linear-gradient(to right, var(--dp-surface) 30%, transparent) left / var(--dp-space-5) 100%,
    linear-gradient(to left, var(--dp-surface) 30%, transparent) right / var(--dp-space-5) 100%,
    radial-gradient(farthest-side at 0 50%, var(--dp-shadow-soft), transparent) left / var(--dp-space-3) 100%,
    radial-gradient(farthest-side at 100% 50%, var(--dp-shadow-soft), transparent) right / var(--dp-space-3) 100%;
  background-color: var(--dp-surface);
  background-repeat: no-repeat;
  background-attachment: local, local, scroll, scroll;
}

.grid-header__group {
  display: flex;
  align-items: stretch;
  flex: none;
}

.grid-header__group-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 0 var(--dp-space-half);
}

.grid-header__label {
  padding-left: var(--dp-space-2);
  font-size: var(--dp-font-size);
  font-weight: 600;
  line-height: 1.4;
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
</style>
