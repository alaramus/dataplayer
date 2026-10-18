<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { t } from "@/shared/i18n"
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
    <!-- One row, scrolling sideways: items keep their text width and never
         wrap, so narrowing the panel scrolls instead of restacking them. -->
    <div class="column-manager__items dp-scroll-edges">
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
          :tooltip="t('grid.columns.move_up', { column: column.label })"
          :disable="index === 0"
          compact
          :data-testid="`grid-column-up-${column.id}`"
          @click="emit('update:layout', moveColumn(layout, column.id, -1))"
        />
        <AppIconButton
          :icon="appIcons.arrowDownward"
          :tooltip="t('grid.columns.move_down', { column: column.label })"
          :disable="index === orderedColumns.length - 1"
          compact
          :data-testid="`grid-column-down-${column.id}`"
          @click="emit('update:layout', moveColumn(layout, column.id, 1))"
        />
        <AppIconButton
          :icon="appIcons.pushPin"
          :active="layout.pinnedLeft.includes(column.id)"
          :aria-pressed="layout.pinnedLeft.includes(column.id)"
          :tooltip="layout.pinnedLeft.includes(column.id) ? t('grid.columns.unpin', { column: column.label }) : t('grid.columns.pin', { column: column.label })"
          compact
          :data-testid="`grid-pin-${column.id}`"
          @click="togglePin(column.id)"
        />
      </div>
    </div>
    <div class="column-manager__foot">
      <AppButton
        :label="t('grid.columns.reset')"
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
  flex-direction: row;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-1) var(--dp-space-2);
  border-top: 1px solid var(--dp-border-faint);
}
.column-manager__items {
  display: flex;
  flex: 1;
  flex-wrap: nowrap;
  gap: 0 var(--dp-space-5);
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
}
.column-manager__item {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--dp-space-half);
  flex: 0 0 auto;
  min-width: 0;
  max-width: var(--dp-width-popover);
  min-height: var(--dp-row-height-dense);
}
.column-manager__visible {
  /* Packs against its buttons rather than pushing them to the item's far edge. */
  flex: 0 1 auto;
  min-width: 0;
}
.column-manager__visible :deep(.q-checkbox__label) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.column-manager__foot {
  display: flex;
  flex: none;
  justify-content: flex-end;
}
</style>
