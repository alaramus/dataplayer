<script setup lang="ts">
import { computed } from "vue"

import { connectorNameOf, useAdapterTypes, useConnectors } from "@/features/connectors/api"
import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppButton, AppTooltip } from "@/shared/ui"

import { terminalCandidates, terminalPress, terminalPressTooltip } from "./terminals"
import { useTerminals } from "./useTerminals"

/**
 * The switch of the Terminals tool in the panel at the foot of the workspace
 * (D143). Pressed in a connection that has a shell, it goes to that
 * connection's terminal, opening one if there is none; anywhere else it shows
 * the panel, which offers the connections that have one (D149).
 */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })

const panel = useBottomPanel()
const workspace = useWorkspaceActions()
const terminals = useTerminals()
const connectors = useConnectors()
const types = useAdapterTypes()

const shown = computed(() => panel.open.value === "terminals")
const press = computed(() =>
  terminalPress({
    shown: shown.value,
    activeConnectorId: workspace.activeConnectorId.value,
    candidateIds: terminalCandidates(connectors.data.value?.data ?? [], types.data.value ?? []).map(
      (connector) => connector.id
    ),
    open: terminals.sessions.value,
  })
)
const tooltip = computed(() =>
  terminalPressTooltip(
    press.value,
    connectorNameOf(connectors.data.value, workspace.activeConnectorId.value)
  )
)

function pressed() {
  const next = press.value
  if (next.kind === "hide") {
    panel.hide()
    return
  }
  if (next.kind === "open") terminals.openOn(next.connectorId)
  else if (next.kind === "select") terminals.select(next.terminalId)
  panel.show("terminals")
}
</script>

<template>
  <!-- The tooltip hangs off this rather than off the button, as the other
       commands on the rails do. -->
  <span class="terminal-command">
    <AppButton
      :variant="shown ? 'secondary' : 'quiet'"
      size="sm"
      icon="terminal"
      :label="iconOnly ? undefined : 'Terminals'"
      :aria-pressed="shown"
      data-testid="command-terminals"
      @click="pressed"
    />
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </span>
</template>

<style scoped>
.terminal-command {
  display: flex;
  align-items: center;
}
</style>
