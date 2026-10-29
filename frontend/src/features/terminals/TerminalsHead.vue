<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { adapterIcon } from "@/features/connectors/adapters"
import { connectorColorOf, connectorNameOf, useConnectors } from "@/features/connectors/api"
import { t } from "@/shared/i18n"
import { AppIconButton, AppMenu, AppTaskbar, AppTaskbarItem } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

import { terminalTitle } from "./terminals"
import type { OpenTerminal } from "./terminals"
import { useTerminalCandidates } from "./useTerminalCandidates"
import { useTerminals } from "./useTerminals"

/**
 * The terminals in the head of the panel: a tab each, and the way to open
 * another. In the head rather than a row of the body, which the screen of a
 * terminal wants whole.
 *
 * Nothing until one is open: before that the panel's own list is the one way
 * to open a terminal, and a plus beside it read as a second, different thing
 * to press.
 */
const terminals = useTerminals()
const connectors = useConnectors()
const candidates = useTerminalCandidates()

const menu = computed<MenuItem[]>(() =>
  candidates.value.length === 0
    ? [
        {
          name: "none",
          label: t("terminals.none_menu"),
          disable: true,
          hint: t("terminals.none_menu_hint"),
        },
      ]
    : candidates.value.map((connector) => ({
        name: connector.id,
        label: connector.name,
        icon: adapterIcon(connector.adapter_type),
      }))
)

function titleOf(terminal: OpenTerminal): string {
  return terminalTitle(terminal, connectorNameOf(connectors.data.value, terminal.connectorId))
}

function open(connectorId: string) {
  if (connectorId === "none") return
  terminals.openOn(connectorId)
}
</script>

<template>
  <div
    v-if="terminals.sessions.value.length > 0"
    class="terminals-head"
  >
    <AppTaskbar :label="t('terminals.terminals')">
      <AppTaskbarItem
        v-for="terminal in terminals.sessions.value"
        :key="terminal.id"
        :title="titleOf(terminal)"
        :icon="appIcons.terminal"
        :color="connectorColorOf(connectors.data.value, terminal.connectorId)"
        :front="terminal.id === terminals.active.value?.id"
        :close-label="t('terminals.close')"
        :close-test-id="`terminal-close-${terminal.id}`"
        :data-testid="`terminal-tab-${terminal.id}`"
        @open="terminals.select(terminal.id)"
        @close="terminals.close(terminal.id)"
      />
    </AppTaskbar>
    <span class="terminals-head__new">
      <AppIconButton
        :icon="appIcons.add"
        :tooltip="t('terminals.open')"
        data-testid="terminal-new"
      />
      <AppMenu
        :items="menu"
        @select="open"
      />
    </span>
  </div>
</template>

<style scoped>
.terminals-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  min-width: 0;
  margin-inline-start: var(--dp-space-2);
}
.terminals-head__new {
  display: flex;
  flex: none;
}
</style>
