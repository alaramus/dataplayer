<script setup lang="ts">
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
    <div
      v-for="(column, index) in orderedColumns"
      :key="column.id"
      class="column-manager__item"
    >
      <AppCheckbox
        :model-value="layout.columnVisibility[column.id] !== false"
        :label="column.label"
        dense
        :data-testid="`grid-column-visible-${column.id}`"
        @update:model-value="setVisible(column.id, $event)"
      />
      <AppIconButton
        icon="arrow_upward"
        :tooltip="`Move ${column.label} up`"
        :disable="index === 0"
        :data-testid="`grid-column-up-${column.id}`"
        @click="emit('update:layout', moveColumn(layout, column.id, -1))"
      />
      <AppIconButton
        icon="arrow_downward"
        :tooltip="`Move ${column.label} down`"
        :disable="index === orderedColumns.length - 1"
        :data-testid="`grid-column-down-${column.id}`"
        @click="emit('update:layout', moveColumn(layout, column.id, 1))"
      />
      <AppButton
        :label="layout.pinnedLeft.includes(column.id) ? 'Unpin' : 'Pin left'"
        variant="quiet"
        size="sm"
        :data-testid="`grid-pin-${column.id}`"
        @click="togglePin(column.id)"
      />
    </div>
    <AppButton
      label="Reset layout"
      variant="quiet"
      size="sm"
      data-testid="grid-columns-reset"
      @click="emit('update:layout', defaultColumnLayout(columns))"
    />
  </div>
</template>

<style scoped>
.column-manager,
.column-manager__item {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.column-manager {
  flex-wrap: wrap;
  min-height: 48px;
  padding: var(--dp-space-1) var(--dp-space-2);
  border-top: 1px solid var(--dp-border-faint);
}

.column-manager__item {
  padding: 0 var(--dp-space-1) 0 var(--dp-space-2);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
}
</style>
