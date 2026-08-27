<script setup lang="ts">
import { computed } from "vue"

import type { FetchColumn } from "@/client"
import { AppButton, AppCheckbox, AppIconButton } from "@/shared/ui"

import { defaultColumnLayout, moveColumn } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"

const props = defineProps<{ columns: FetchColumn[]; layout: ColumnLayoutState }>()
const emit = defineEmits<{ "update:layout": [layout: ColumnLayoutState]; close: [] }>()

const byName = computed(() => new Map(props.columns.map((column) => [column.name, column])))
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
      :key="column.name"
      class="column-manager__item"
    >
      <AppCheckbox
        :model-value="layout.columnVisibility[column.name] !== false"
        :label="column.name"
        dense
        @update:model-value="setVisible(column.name, $event)"
      />
      <AppIconButton
        icon="arrow_upward"
        :tooltip="`Move ${column.name} up`"
        :disable="index === 0"
        :data-testid="`grid-column-up-${column.name}`"
        @click="emit('update:layout', moveColumn(layout, column.name, -1))"
      />
      <AppIconButton
        icon="arrow_downward"
        :tooltip="`Move ${column.name} down`"
        :disable="index === orderedColumns.length - 1"
        :data-testid="`grid-column-down-${column.name}`"
        @click="emit('update:layout', moveColumn(layout, column.name, 1))"
      />
      <AppButton
        :label="layout.pinnedLeft.includes(column.name) ? 'Unpin' : 'Pin left'"
        variant="quiet"
        size="sm"
        :data-testid="`grid-pin-${column.name}`"
        @click="togglePin(column.name)"
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
  gap: 6px;
}

.column-manager {
  flex-wrap: wrap;
  min-height: 48px;
  padding: 4px 8px;
  border-top: 1px solid var(--dp-border-faint);
}

.column-manager__item {
  padding: 0 4px 0 8px;
  border: 1px solid var(--dp-border);
  border-radius: 4px;
}
</style>
