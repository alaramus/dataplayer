<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { nextTick, ref } from "vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppIconButton, AppInput } from "@/shared/ui"

/**
 * The head of the column of connections, where its tab used to be.
 *
 * The column holds nothing else and the panel can be neither closed nor
 * carried anywhere, so the tab only said "Connections". The name first and the
 * commands after it, as every other head of a list has them — Dashboards,
 * Pipelines — with re-reading the list at the end, where every panel keeps
 * what it offers about itself (D112). The rail of a collapsed column keeps
 * the commands without the name.
 *
 * Pipelines stands on the same list and draws this same head over it, filter
 * included, so switching between the two spaces changes nothing on that card.
 */
const workspace = useWorkspaceActions()
const head = ref<HTMLElement | null>(null)

async function openFilter() {
  workspace.connectorFilterOpen.value = true
  await nextTick()
  head.value?.querySelector("input")?.focus()
}

function closeFilter() {
  workspace.connectorNameFilter.value = ""
  workspace.connectorFilterOpen.value = false
}
</script>

<template>
  <div
    ref="head"
    class="connectors-head"
    role="toolbar"
    aria-label="Connections"
    data-testid="connectors-head"
    @keydown.esc.stop="closeFilter"
  >
    <template v-if="workspace.connectorFilterOpen.value">
      <AppInput
        :model-value="workspace.connectorNameFilter.value"
        class="connectors-head__filter"
        placeholder="Filter connections"
        aria-label="Filter connections by name"
        autocomplete="off"
        compact
        data-testid="connectors-name-filter"
        @update:model-value="workspace.connectorNameFilter.value = $event"
      />
      <AppIconButton
        :icon="appIcons.close"
        tooltip="Close connection filter"
        data-testid="connectors-filter-close"
        @click="closeFilter"
      />
    </template>
    <template v-else>
      <span class="connectors-head__title">Connections</span>
      <AppIconButton
        :icon="appIcons.add"
        tooltip="New connection"
        data-testid="add-connector"
        @click="workspace.editConnector(null)"
      />
      <AppIconButton
        :icon="appIcons.search"
        tooltip="Filter connections by name"
        data-testid="connectors-filter-open"
        @click="openFilter"
      />
      <span class="connectors-head__commands">
        <PanelCommands panel-id="connectors" />
      </span>
    </template>
  </div>
</template>

<style scoped>
.connectors-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
}
.connectors-head__filter {
  flex: 1;
  min-width: 0;
}
.connectors-head__filter :deep(.q-field__control),
.connectors-head__filter :deep(.q-field__marginal),
.connectors-head__filter :deep(.q-field__native) {
  height: calc(var(--dp-tab-strip-height) - 1px);
  min-height: calc(var(--dp-tab-strip-height) - 1px);
}
/* Takes the room left, so the commands stand at the right-hand end. */
.connectors-head__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.connectors-head__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
</style>
