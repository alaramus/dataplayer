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
    class="app-table"
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
/* A table's heading is a heading of the scale (D185): 600, in the small size
   Quasar already gives it; Quasar's own 500 was the one table in the
   application whose headings were not. */
.app-table :deep(thead th) {
  font-weight: 600;
}
/* The rows scroll, the header does not. Quasar builds the table out of nested
   elements, so the height has to be handed down to the one that scrolls.

   The background belongs here rather than on a descendant: the class lands on
   the same element Quasar calls `q-table__container`, which is what carries
   the table's own card — white, and #1d1d1d in the dark theme. Over a panel
   that is `--dp-surface` that made three colours out of one column: the panel,
   the card on it, and the sticky heading on that. A table filling a panel is
   not a card; it takes the surface it was put on. */
.app-table--sticky {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--dp-surface);
}
.app-table--sticky :deep(.q-table__middle) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
/* The same value as the table above, and that is the point: a sticky
   heading's whole job is to hide the rows sliding under it, so a heading that
   is not exactly the colour of its own table is a stripe across it. */
.app-table--sticky :deep(thead tr th) {
  position: sticky;
  top: 0;
  z-index: var(--dp-layer-sticky);
  background: var(--dp-surface);
}
</style>
