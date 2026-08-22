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
  }>(),
  { loading: false, emptyText: "Nothing to show", compact: false, paged: true }
)
</script>

<template>
  <q-table
    flat
    bordered
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
