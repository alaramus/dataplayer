<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { AppButton, AppCheckbox, AppIconButton } from "@/shared/ui"

import { defaultColumnLayout, moveColumn } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"
import type { TabularColumn } from "./tabular"

const props = defineProps<{ columns: TabularColumn[]; layout: ColumnLayoutState }>()
const emit = defineEmits<{ "update:layout": [layout: ColumnLayoutState]; close: [] }>()

const byName = computed(() => new Map(props.columns.map((column) => [column.id, column])))
const orderedColumns = computed(() =>
  props.layout.columnOrder.flatMap((name) => {
    const column = byName.value.get(name)
    return column === undefined ? [] : [column]
  })
)

function setVisible(columnName: string, visible: boolean) {
  emit("update:layout", {
    ...props.layout,
    columnVisibility: { ...props.layout.columnVisibility, [columnName]: visible },
  })
}

function togglePin(columnName: string) {
  const pinned = props.layout.pinnedLeft.includes(columnName)
    ? props.layout.pinnedLeft.filter((name) => name !== columnName)
    : [...props.layout.pinnedLeft, columnName]
  emit("update:layout", { ...props.layout, pinnedLeft: pinned })
}
</script>

<template>
  <div
    class="column-manager"
    data-testid="grid-column-manager"
    @keyup.esc="emit('close')"
  >
    <!-- One column of the grid a cell: every cell the same width, so the
         checkboxes stand under each other instead of a wrapped row of boxes
         of every length, and pinning is the header's own pin (D187). -->
    <div class="column-manager__items">
      <div
        v-for="(column, index) in orderedColumns"
        :key="column.id"
        class="column-manager__item"
      >
        <AppCheckbox
          class="column-manager__visible"
          :model-value="layout.columnVisibility[column.id] !== false"
          :label="column.label"
          dense
          :data-testid="`grid-column-visible-${column.id}`"
          @update:model-value="setVisible(column.id, $event)"
        />
        <AppIconButton
          :icon="appIcons.arrowUpward"
          :tooltip="`Move ${column.label} up`"
          :disable="index === 0"
          compact
          :data-testid="`grid-column-up-${column.id}`"
          @click="emit('update:layout', moveColumn(layout, column.id, -1))"
        />
        <AppIconButton
          :icon="appIcons.arrowDownward"
          :tooltip="`Move ${column.label} down`"
          :disable="index === orderedColumns.length - 1"
          compact
          :data-testid="`grid-column-down-${column.id}`"
          @click="emit('update:layout', moveColumn(layout, column.id, 1))"
        />
        <AppIconButton
          :icon="appIcons.pushPin"
          :active="layout.pinnedLeft.includes(column.id)"
          :aria-pressed="layout.pinnedLeft.includes(column.id)"
          :tooltip="layout.pinnedLeft.includes(column.id) ? `Unpin ${column.label}` : `Pin ${column.label} to the left`"
          compact
          :data-testid="`grid-pin-${column.id}`"
          @click="togglePin(column.id)"
        />
      </div>
    </div>
    <div class="column-manager__foot">
      <AppButton
        label="Reset layout"
        variant="quiet"
        size="sm"
        data-testid="grid-columns-reset"
        @click="emit('update:layout', defaultColumnLayout(columns))"
      />
    </div>
  </div>
</template>

<style scoped>
.column-manager {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  padding: var(--dp-space-1) var(--dp-space-2);
  border-top: 1px solid var(--dp-border-faint);
}
.column-manager__items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0 var(--dp-space-3);
  max-height: calc(6 * var(--dp-row-height));
  overflow: auto;
}
.column-manager__item {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
  min-width: 0;
  min-height: var(--dp-row-height-dense);
}
.column-manager__visible {
  flex: 1;
  min-width: 0;
}
.column-manager__visible :deep(.q-checkbox__label) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.column-manager__foot {
  display: flex;
  justify-content: flex-end;
}
</style>
