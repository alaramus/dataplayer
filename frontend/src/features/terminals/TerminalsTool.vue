<script setup lang="ts">
import { computed, ref } from "vue"

import type { SshKeyPublic } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"
import UnlockKeyDialog from "@/features/sshKeys/UnlockKeyDialog.vue"
import { useLockedKey } from "@/features/sshKeys/api"
import { t } from "@/shared/i18n"
import { AppBanner, AppButton, AppEmptyState } from "@/shared/ui"

import TerminalView from "./TerminalView.vue"
import { terminalNotice } from "./terminals"
import { useTerminalCandidates } from "./useTerminalCandidates"
import { useTerminals } from "./useTerminals"

/**
 * The terminals, as a tool of the panel at the foot of the workspace (D143,
 * D149): the one in front, or, while none is open, the connections one can
 * be opened on. Their tabs and the way to open another are in the head of the
 * panel, `TerminalsHead`.
 */
const terminals = useTerminals()
const candidates = useTerminalCandidates()

const current = terminals.active
const notice = computed(() => (current.value ? terminalNotice(current.value.state) : null))

/** The key to open, when the shell was refused because it is locked (D147). */
const lockedKey = useLockedKey(
  () => current.value?.connectorId ?? "",
  () => (notice.value?.action === "unlock" ? "locked" : null)
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
            :label="t('terminals.open_again')"
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
            :label="t('terminals.unlock')"
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
            ? t('terminals.none')
            : t('terminals.choose')
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
          @click="terminals.openOn(connector.id)"
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
.terminals__choice {
  display: flex;
  flex-direction: column;
  padding-right: var(--dp-space-2);
  gap: var(--dp-space-2);
}
.terminals__candidates {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-1);
}
</style>
