<script setup lang="ts">
import type { QTableProps } from "quasar"

/** Quasar exports no column type of its own, so it is read off the props. */
export type TableColumns = NonNullable<QTableProps["columns"]>

withDefaults(
  defineProps<{
    rows: readonly Record<string, unknown>[]
    columns: TableColumns
    rowKey: string
    loading?: boolean
    /** What to say when there is nothing, instead of Quasar's own wording. */
    emptyText?: string
    /** A grid of data rather than a list of things: tighter rows. */
    compact?: boolean
    /** Off when the caller pages the data itself against the server. */
    paged?: boolean
    /**
     * Fill the box the caller gave it and scroll inside: the header stays put
     * while the rows move. Without it the table is as tall as its rows and
     * whatever holds it has to deal with that.
     */
    sticky?: boolean
  }>(),
  {
    loading: false,
    emptyText: "Nothing to show",
    compact: false,
    paged: true,
    sticky: false,
  }
)
</script>

<template>
  <q-table
    flat
    bordered
    :class="sticky ? 'app-table--sticky' : undefined"
    :rows="rows"
    :columns="columns"
    :row-key="rowKey"
    :loading="loading"
    :dense="compact"
    :no-data-label="emptyText"
    :hide-pagination="!paged"
    :rows-per-page-options="paged ? undefined : [0]"
  >
    <!--
      The only place in the kit that forwards slots by iterating rather than by
      name. A table's cell slots are named after the columns, so the names are
      not known here; enumerating them would mean the kit knowing every screen.
    -->
    <template
      v-for="name in Object.keys($slots)"
      :key="name"
      #[name]="slotProps"
    >
      <slot
        :name="name"
        v-bind="slotProps ?? {}"
      />
    </template>
  </q-table>
</template>

<style scoped>
/* The rows scroll, the header does not. Quasar builds the table out of nested
   elements, so the height has to be handed down to the one that scrolls. */
.app-table--sticky {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.app-table--sticky :deep(.q-table__middle) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.app-table--sticky :deep(thead tr th) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--dp-surface);
}
</style>
