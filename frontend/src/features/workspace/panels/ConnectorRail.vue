<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import ConnectorIcon from "@/features/connectors/ConnectorIcon.vue"
import { useConnectors } from "@/features/connectors/api"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppCardHead, AppIconButton, AppScrollArea } from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"

/**
 * The connections while their column is pushed aside. The name goes, because
 * at forty pixels it is one letter; a click opens the catalog rather than the
 * window, which opens from the head of the catalog anyway.
 *
 * Adding one survives the width too, and makes the same call the wide panel
 * makes rather than its own copy of what "new connection" means.
 */
const workspace = useWorkspaceActions()
const connectors = useConnectors()

const rows = computed(() => connectors.data.value?.data ?? [])
</script>

<template>
  <div
    class="connector-rail"
    data-testid="connector-rail"
  >
    <!-- In a head of its own, as the wide column has one: the section stands
         its strip down while collapsed, and the plus keeps its place.

         The same test id the wide head carries, because it is the same
         action: the two never exist at the same time. -->
    <AppCardHead class="connector-rail__head">
      <AppIconButton
        :icon="appIcons.add"
        tooltip="New connection"
        data-testid="add-connector"
        @click="workspace.editConnector(null)"
      />
    </AppCardHead>

    <!-- Only the icons scroll, under a bar that takes no room: a native one
         took a third of the forty pixels and scrolled the plus away too. -->
    <AppScrollArea>
      <div class="connector-rail__icons">
        <div
          v-for="connector in rows"
          :key="connector.id"
          class="connector-rail__slot"
          :class="{
            'connector-rail__slot--open': workspace.openConnectorIds.value.has(connector.id),
            'connector-rail__slot--selected': connector.id === workspace.activeConnectorId.value,
          }"
          :style="panelColorStyle(connector.tab_color)"
        >
          <ConnectorIcon
            :connector-id="connector.id"
            :name="connector.name"
            :adapter-type="connector.adapter_type"
            :enabled="connector.enabled"
            :tooltip="connector.name"
            :testid="`connector-rail-${connector.name}`"
            @click="workspace.openCatalog(connector)"
          />
        </div>
      </div>
    </AppScrollArea>
  </div>
</template>

<style scoped>
/* The height of the column, so the icons scroll inside it and the head
   stays. */
.connector-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
}
.connector-rail__icons {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-bottom: var(--dp-space-half);
}
/* Centred like the rails of the dashboards and the chats, so the plus sits
   over the connector icons below it. */
.connector-rail .connector-rail__head {
  align-self: stretch;
  justify-content: center;
  margin-bottom: var(--dp-space-1);
  padding: 0;
}
.connector-rail__slot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--dp-radius-control);
}
/* The same two states the wide row carries, at a smaller width — and in the
   connection's own colour for the same reason: pushing the column aside takes
   away the name and nothing else. */
.connector-rail__slot--open {
  background: var(--dp-panel-quiet, var(--dp-panel-plain-quiet));
}
.connector-rail__slot--selected {
  background: var(--dp-panel-background, var(--dp-panel-plain));
}
</style>
