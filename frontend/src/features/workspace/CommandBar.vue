<script setup lang="ts">
import { computed } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { useQueryProfile } from "@/features/queries/runs"
import { queriesCommand } from "@/features/workspace/commands"
import type { Support } from "@/features/workspace/commands"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppButton, AppTooltip } from "@/shared/ui"

/**
 * The commands at the foot of the screen, before the open windows: the
 * library of queries. What acts on the open connection is in the connection's
 * own menu, where the rest of what a connection can do already was, and what
 * is about the machine sits at the far end of the bar.
 *
 * Which connection is not written here. It is already said in the column of
 * connections and on the tab of the catalog, and a third copy took the room
 * the commands want; each tooltip names it where a button leaves doubt (D69).
 */
const workspace = useWorkspaceActions()
const connectors = useConnectors()

const connector = computed(() => {
  const id = workspace.activeConnectorId.value
  if (id === null) return null
  return (connectors.data.value?.data ?? []).find((row) => row.id === id) ?? null
})

/**
 * What this connection says it accepts as a statement.
 *
 * The capability is the answer to that question rather than a flag beside it:
 * a source that does not run queries answers 501 and has no profile at all,
 * which is exactly what "does not run queries" means (D62).
 */
const profile = useQueryProfile(() => workspace.activeConnectorId.value)
const supportsQueries = computed<Support>(() => {
  if (workspace.activeConnectorId.value === null) return "no"
  if (profile.isSuccess.value) return "yes"
  return profile.isError.value ? "no" : "asking"
})

/**
 * The library, which is not the open connection's: it is always pressable,
 * and what it says depends on whether there is a connection to open it
 * against.
 */
const library = computed(() =>
  queriesCommand({
    name: connector.value?.name ?? null,
    supportsQueries: supportsQueries.value,
  })
)
</script>

<template>
  <div
    class="command-bar"
    data-testid="command-bar"
  >
    <!-- Never greyed out: what a person has written is theirs whether or not a
         connection is open. The tooltip hangs off the wrapper, because a
         disabled Quasar button takes no pointer events. -->
    <span class="command-bar__slot">
      <AppButton
        variant="quiet"
        size="sm"
        :icon="library.icon"
        :label="library.label"
        data-testid="command-queries"
        @click="workspace.openQueries(workspace.activeConnectorId.value)"
      />
      <AppTooltip>{{ library.tooltip }}</AppTooltip>
    </span>
  </div>
</template>

<style scoped>
.command-bar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  /* Only as wide as its commands: the room left over belongs to the taskbar
     that follows it. */
  flex: none;
}

.command-bar__slot {
  display: flex;
  align-items: center;
}
</style>
