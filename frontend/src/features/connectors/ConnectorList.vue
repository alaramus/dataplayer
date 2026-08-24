<script setup lang="ts">
import { computed } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorIcon from "@/features/connectors/ConnectorIcon.vue"
import { AppEmptyState, AppSpinner } from "@/shared/ui"

/**
 * The sources of the workspace, one per row.
 *
 * Two things in a row and nothing else: the icon of the source type, carrying
 * what the last check said, and the name beside it. Everything that can be done to a
 * connection lives inside the window its icon opens — a menu here would be a
 * second home for the same commands, and two homes drift. See the spec, S1.
 */
const props = defineProps<{
  rows: ConnectorPublic[]
  loading: boolean
  /** The connection whose catalog is being looked at, if any. */
  selectedId?: string | null
  /**
   * The connections that have a catalog open somewhere.
   *
   * A quieter version of the same mark rather than a fourth thing in the row:
   * a row is an icon, a name and a state dot, and there is nothing to add to
   * it. See P7.
   */
  openIds?: ReadonlySet<string>
}>()

const emit = defineEmits<{
  open: [connector: ConnectorPublic]
  edit: [connector: ConnectorPublic]
}>()

const selected = computed(() => props.selectedId ?? null)
const open = computed(() => props.openIds ?? new Set<string>())
</script>

<template>
  <AppSpinner v-if="loading" />

  <AppEmptyState
    v-else-if="rows.length === 0"
    text="No connections yet"
  />

  <div
    v-else
    class="connector-list"
    data-testid="connector-list"
  >
    <!-- A div and not a button: the row carries the icon button that opens the
         window, and a button inside a button is markup no browser agrees
         about. -->
    <div
      v-for="connector in rows"
      :key="connector.id"
      role="button"
      tabindex="0"
      class="connector-list__row"
      :class="{
        'connector-list__row--open': open.has(connector.id),
        'connector-list__row--selected': connector.id === selected,
      }"
      :data-testid="`connector-${connector.name}`"
      :data-connector-id="connector.id"
      @click="emit('open', connector)"
      @keydown.enter="emit('open', connector)"
      @keydown.space.prevent="emit('open', connector)"
    >
      <!-- The icon carries the state dot, exactly as it does in the strip a
           collapsed column leaves behind: what a press means differs, what is
           drawn does not. -->
      <span @click.stop>
        <ConnectorIcon
          :connector-id="connector.id"
          :name="connector.name"
          :adapter-type="connector.adapter_type"
          tooltip="Edit connection"
          :testid="`connector-edit-${connector.name}`"
          @click="emit('edit', connector)"
        />
      </span>

      <span class="connector-list__name">{{ connector.name }}</span>
    </div>
  </div>
</template>

<style scoped>
.connector-list {
  display: flex;
  flex-direction: column;
}
.connector-list__row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  /* The same four pixels the strip centres its icons at, so that a row keeps
     its icon in place when the column is pushed aside. */
  padding: 1px 8px 1px 4px;
  cursor: pointer;
}
.connector-list__row:hover {
  background: var(--dp-hover);
}
/* Open somewhere, and the one being read. The full mark is written after the
   quiet one so that it wins where both apply. */
.connector-list__row--open {
  background: var(--dp-selected-quiet);
}
.connector-list__row--selected {
  background: var(--dp-selected);
  font-weight: 500;
}
.connector-list__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
