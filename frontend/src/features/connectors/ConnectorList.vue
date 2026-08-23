<script setup lang="ts">
import { computed } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorDot from "@/features/connectors/ConnectorDot.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import { AppEmptyState, AppIconButton, AppSpinner } from "@/shared/ui"

/**
 * The sources of the workspace, one per row.
 *
 * Three things in a row and nothing else: what kind of source it is, what it
 * is called, and what the last check said. Everything that can be done to a
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
      @click="emit('open', connector)"
      @keydown.enter="emit('open', connector)"
      @keydown.space.prevent="emit('open', connector)"
    >
      <span @click.stop>
        <AppIconButton
          :icon="adapterIcon(connector.adapter_type)"
          tooltip="Edit connection"
          :data-testid="`connector-edit-${connector.name}`"
          @click="emit('edit', connector)"
        />
      </span>

      <span class="connector-list__name">{{ connector.name }}</span>

      <!-- What the last check said, and nothing more: no check has been made
           until the user asks for one. -->
      <ConnectorDot
        :connector-id="connector.id"
        :name="connector.name"
      />
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
  padding: 1px 8px;
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
