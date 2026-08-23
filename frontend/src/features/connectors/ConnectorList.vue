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
  /** The connection whose catalog is showing, if any. */
  selectedId?: string | null
}>()

const emit = defineEmits<{
  open: [connector: ConnectorPublic]
  edit: [connector: ConnectorPublic]
}>()

const selected = computed(() => props.selectedId ?? null)
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
      :class="{ 'connector-list__row--selected': connector.id === selected }"
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
  background: rgba(0, 0, 0, 0.04);
}
.connector-list__row--selected {
  background: rgba(25, 118, 210, 0.1);
  font-weight: 500;
}
.connector-list__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
