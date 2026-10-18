<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { nextTick, ref } from "vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useWorkspaceActions } from "@/features/workspace/state"
import { t } from "@/shared/i18n"
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
    :aria-label="t('workspace.connectors.title')"
    data-testid="connectors-head"
    @keydown.esc.stop="closeFilter"
  >
    <template v-if="workspace.connectorFilterOpen.value">
      <AppInput
        :model-value="workspace.connectorNameFilter.value"
        class="connectors-head__filter"
        :placeholder="t('workspace.connectors.filter')"
        :aria-label="t('workspace.connectors.filter_by_name')"
        autocomplete="off"
        compact
        data-testid="connectors-name-filter"
        @update:model-value="workspace.connectorNameFilter.value = $event"
      />
      <AppIconButton
        :icon="appIcons.close"
        :tooltip="t('workspace.connectors.close_filter')"
        data-testid="connectors-filter-close"
        @click="closeFilter"
      />
    </template>
    <template v-else>
      <span
        class="connectors-head__title"
        :title="t('workspace.connectors.title')"
      >{{ t('workspace.connectors.title') }}</span>
      <AppIconButton
        :icon="appIcons.add"
        :tooltip="t('workspace.connectors.new')"
        data-testid="add-connector"
        @click="workspace.editConnector(null)"
      />
      <AppIconButton
        :icon="appIcons.search"
        :tooltip="t('workspace.connectors.filter_by_name')"
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
}
.connectors-head__filter {
  flex: 1;
  min-width: 0;
  margin-right: var(--dp-space-1);
  --dp-field-height: calc(var(--dp-tab-strip-height) - 1px);
}
/* Takes the room left and shortens with an ellipsis like every other head,
   so the name stays readable however narrow the column is. */
.connectors-head__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  margin-right: var(--dp-space-half);
}
.connectors-head__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
</style>
