<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { Sort } from "@/client"
import { t } from "@/shared/i18n"
import { AppButton, AppIconButton, AppSelect } from "@/shared/ui"

import { moveSort } from "./sortModel"
import type { TabularColumn } from "./tabular"

const props = defineProps<{ columns: TabularColumn[]; sort: Sort[] }>()
const emit = defineEmits<{ apply: [sort: Sort[]]; close: [] }>()

const sortableColumns = computed(() => props.columns.filter((column) => column.sortable === true))
const availableColumns = computed(() =>
  sortableColumns.value.filter(
    (column) => !props.sort.some((item) => item.column === column.id)
  )
)
const selectedColumn = ref<string | null>(null)
const addOptions = computed(() =>
  availableColumns.value.map((column) => ({ label: column.label, value: column.id }))
)

function addColumn() {
  const column =
    selectedColumn.value ?? (availableColumns.value.length === 1 ? availableColumns.value[0]?.id : null)
  if (column === null || column === undefined) return
  emit("apply", [...props.sort, { column, descending: false }])
  selectedColumn.value = null
}

function toggleDirection(index: number) {
  emit(
    "apply",
    props.sort.map((item, itemIndex) =>
      itemIndex === index ? { ...item, descending: item.descending !== true } : item
    )
  )
}

function remove(index: number) {
  emit(
    "apply",
    props.sort.filter((_, itemIndex) => itemIndex !== index)
  )
}
</script>

<template>
  <div
    class="sort-editor"
    data-testid="grid-sort-editor"
    @keyup.esc="emit('close')"
  >
    <div
      v-for="(item, index) in sort"
      :key="item.column"
      class="sort-editor__item"
    >
      <span class="sort-editor__priority">{{ index + 1 }}</span>
      <span>{{ columns.find((column) => column.id === item.column)?.label ?? item.column }}</span>
      <AppButton
        :label="item.descending === true ? t('grid.sort.descending') : t('grid.sort.ascending')"
        variant="quiet"
        size="sm"
        :data-testid="`grid-sort-direction-${index}`"
        @click="toggleDirection(index)"
      />
      <AppIconButton
        :icon="appIcons.arrowUpward"
        :tooltip="t('grid.columns.move_up', { column: item.column })"
        :disable="index === 0"
        :data-testid="`grid-sort-up-${index}`"
        @click="emit('apply', moveSort(sort, index, -1))"
      />
      <AppIconButton
        :icon="appIcons.arrowDownward"
        :tooltip="t('grid.columns.move_down', { column: item.column })"
        :disable="index === sort.length - 1"
        :data-testid="`grid-sort-down-${index}`"
        @click="emit('apply', moveSort(sort, index, 1))"
      />
      <AppIconButton
        :icon="appIcons.close"
        :tooltip="t('grid.sort.remove', { column: item.column })"
        :data-testid="`grid-sort-delete-${index}`"
        @click="remove(index)"
      />
    </div>

    <span
      v-if="sort.length === 0"
      class="sort-editor__empty"
    >{{ t('grid.sort.none') }}</span>
    <div class="sort-editor__add">
      <AppSelect
        v-model="selectedColumn"
        class="sort-editor__field"
        :options="addOptions"
        :label="t('grid.column')"
        compact
        :disable="availableColumns.length === 0"
      />
      <AppButton
        :label="t('grid.add')"
        variant="quiet"
        size="sm"
        :disable="availableColumns.length === 0"
        data-testid="grid-sort-add"
        @click="addColumn"
      />
      <AppButton
        :label="t('grid.clear_all')"
        variant="quiet"
        size="sm"
        :disable="sort.length === 0"
        data-testid="grid-sort-clear"
        @click="emit('apply', [])"
      />
    </div>
  </div>
</template>

<style scoped>
.sort-editor,
.sort-editor__item,
.sort-editor__add {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.sort-editor {
  flex-wrap: wrap;
  min-height: calc(var(--dp-toolbar-height) + 2 * var(--dp-space-1));
  padding: var(--dp-space-1) var(--dp-space-2);
  border-top: 1px solid var(--dp-border-faint);
}

.sort-editor__item {
  padding-left: var(--dp-space-2);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
}

.sort-editor__priority,
.sort-editor__empty {
  color: var(--dp-text-muted);
}

.sort-editor__field {
  min-width: 140px;
}
</style>
