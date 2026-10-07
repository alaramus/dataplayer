<script setup lang="ts">
import { computed, watch } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { useQueryProfile } from "@/features/queries/runs"
import { queriesCommand } from "@/features/workspace/commands"
import type { Support } from "@/features/workspace/commands"
import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppButton, AppTooltip } from "@/shared/ui"

import { useQueriesLibrary } from "./library"

/**
 * The switch of the query library in the panel at the foot of the workspace
 * (D143), beside Services and Terminals. Pressed while a connection is being
 * read, the library opens filtered to it (D69).
 */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })

const workspace = useWorkspaceActions()
const connectors = useConnectors()
const panel = useBottomPanel()
const library = useQueriesLibrary()

const connector = computed(() => {
  const id = workspace.activeConnectorId.value
  if (id === null) return null
  return (connectors.data.value?.data ?? []).find((row) => row.id === id) ?? null
})

/**
 * What this connection says it accepts as a statement. The capability is the
 * answer: a source that does not run queries answers 501 and has no profile
 * at all (D62).
 */
const profile = useQueryProfile(() => workspace.activeConnectorId.value)
const supportsQueries = computed<Support>(() => {
  if (workspace.activeConnectorId.value === null) return "no"
  if (profile.isSuccess.value) return "yes"
  return profile.isError.value ? "no" : "asking"
})

const command = computed(() =>
  queriesCommand({
    name: connector.value?.name ?? null,
    supportsQueries: supportsQueries.value,
  })
)
const shown = computed(() => panel.open.value === "queries")

function pressed() {
  if (shown.value) {
    panel.hide()
    return
  }
  if (supportsQueries.value === "yes") library.aim(workspace.activeConnectorId.value)
  panel.show("queries")
}

/**
 * Aim late, when the profile lands after the press.
 *
 * The capability is asked of the source, so a press that opens the panel
 * while it is still being asked leaves the library unaimed — and its New
 * button stays disabled until somebody picks a connection by hand. Only an
 * unpicked filter is aimed: what somebody chose stays chosen.
 */
watch([shown, supportsQueries], ([open, support]) => {
  if (open && support === "yes" && library.connectorId.value === null) {
    library.aim(workspace.activeConnectorId.value)
  }
})
</script>

<template>
  <!-- The tooltip hangs off this rather than off the button, as the other
       commands on the rails do. -->
  <span class="queries-command">
    <AppButton
      :variant="shown ? 'chosen' : 'quiet'"
      size="sm"
      :icon="command.icon"
      :label="command.label"
      :icon-only="iconOnly"
      :aria-pressed="shown"
      data-testid="command-queries"
      @click="pressed"
    />
    <AppTooltip>{{ command.tooltip }}</AppTooltip>
  </span>
</template>

<style scoped>
.queries-command {
  display: flex;
  align-items: center;
}
</style>
