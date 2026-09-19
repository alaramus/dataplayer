<script setup lang="ts">
import { computed, ref } from "vue"

import type { SshKeyPublic } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"
import {
  connectorColorOf,
  connectorNameOf,
  useAdapterTypes,
  useConnectors,
} from "@/features/connectors/api"
import UnlockKeyDialog from "@/features/sshKeys/UnlockKeyDialog.vue"
import { useSshKeys } from "@/features/sshKeys/api"
import { keyUsedBy } from "@/features/sshKeys/keys"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppMenu,
  AppTaskbar,
  AppTaskbarItem,
} from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

import TerminalView from "./TerminalView.vue"
import { terminalCandidates, terminalNotice, terminalTitle } from "./terminals"
import type { OpenTerminal } from "./terminals"
import { useTerminals } from "./useTerminals"

/**
 * The terminals, as a tool of the panel at the foot of the workspace (D143,
 * D149): one tab each, the one in front drawn below, and a way to open
 * another on any connection of one's own that has a shell.
 */
const terminals = useTerminals()
const connectors = useConnectors()
const types = useAdapterTypes()

const candidates = computed(() =>
  terminalCandidates(connectors.data.value?.data ?? [], types.data.value ?? [])
)
const menu = computed<MenuItem[]>(() =>
  candidates.value.length === 0
    ? [
        {
          name: "none",
          label: "No connection of yours has a terminal",
          disable: true,
          hint: "An SSH connection does",
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

const current = terminals.active
const notice = computed(() => (current.value ? terminalNotice(current.value.state) : null))

/** The key to open, when the shell was refused because it is locked (D147). */
const locked = computed(() => notice.value?.action === "unlock")
const sshKeys = useSshKeys(locked)
const lockedKey = computed<SshKeyPublic | null>(() =>
  locked.value && current.value
    ? keyUsedBy(sshKeys.data.value ?? [], current.value.connectorId)
    : null
)
const unlocking = ref<SshKeyPublic | null>(null)
/** Which terminal the unlock was asked from: it is opened again once it is done. */
const unlockingFor = ref<string | null>(null)

// A function rather than an inline handler: the template's narrowing of
// `current` does not reach into a closure.
function again() {
  if (current.value) terminals.openAgain(current.value.id)
}

function unlock() {
  if (!lockedKey.value || !current.value) return
  unlockingFor.value = current.value.id
  unlocking.value = lockedKey.value
}

function unlocked() {
  if (unlockingFor.value !== null) terminals.openAgain(unlockingFor.value)
  unlockingFor.value = null
}
</script>

<template>
  <div
    class="terminals"
    data-testid="terminals"
  >
    <div class="terminals__bar">
      <AppTaskbar label="Terminals">
        <AppTaskbarItem
          v-for="terminal in terminals.sessions.value"
          :key="terminal.id"
          :title="titleOf(terminal)"
          icon="terminal"
          :color="connectorColorOf(connectors.data.value, terminal.connectorId)"
          :front="terminal.id === current?.id"
          close-label="Close this terminal"
          :close-test-id="`terminal-close-${terminal.id}`"
          :data-testid="`terminal-tab-${terminal.id}`"
          @open="terminals.select(terminal.id)"
          @close="terminals.close(terminal.id)"
        />
      </AppTaskbar>
      <span class="terminals__new">
        <AppIconButton
          icon="add"
          tooltip="Open a terminal"
          data-testid="terminal-new"
        />
        <AppMenu
          :items="menu"
          @select="open"
        />
      </span>
    </div>

    <template v-if="current">
      <AppBanner
        v-if="notice"
        :tone="notice.tone"
        data-testid="terminal-notice"
      >
        {{ notice.text }}
        <template
          v-if="notice.action === 'again'"
          #action
        >
          <AppButton
            variant="quiet"
            label="Open again"
            data-testid="terminal-open-again"
            @click="again"
          />
        </template>
        <!-- Only the owner's list holds the key, and only the owner has a
             terminal to open, so the button is never offered in vain. -->
        <template
          v-else-if="notice.action === 'unlock' && lockedKey"
          #action
        >
          <AppButton
            variant="quiet"
            label="Unlock the key"
            data-testid="terminal-unlock-key"
            @click="unlock"
          />
        </template>
      </AppBanner>
      <TerminalView
        :key="current.id"
        :session="current"
      />
    </template>
    <div
      v-else
      class="terminals__choice"
    >
      <AppEmptyState
        icon="terminal"
        :text="
          candidates.length === 0
            ? 'None of your connections has a terminal. An SSH connection does.'
            : 'No terminal is open. Open one on a connection of yours:'
        "
      />
      <div class="terminals__candidates">
        <AppButton
          v-for="connector in candidates"
          :key="connector.id"
          variant="secondary"
          size="sm"
          :icon="adapterIcon(connector.adapter_type)"
          :label="connector.name"
          :data-testid="`terminal-open-${connector.name}`"
          @click="open(connector.id)"
        />
      </div>
    </div>

    <UnlockKeyDialog
      :key-id="unlocking?.id ?? null"
      :key-name="unlocking?.name ?? ''"
      @unlocked="unlocked"
      @close="unlocking = null"
    />
  </div>
</template>

<style scoped>
.terminals {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  height: 100%;
  min-height: 0;
}
.terminals__bar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  min-width: 0;
}
.terminals__new {
  display: flex;
  flex: none;
}
.terminals__choice {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
.terminals__candidates {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-1);
}
</style>
