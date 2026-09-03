<script setup lang="ts">
import { computed, ref } from "vue"

import { adapterIcon } from "@/features/connectors/adapters"
import { useConnectors } from "@/features/connectors/api"
import { useQueryProfile } from "@/features/queries/runs"
import BackupsDialog from "@/features/services/BackupsDialog.vue"
import { useBackupOffer } from "@/features/services/api"
import { connectionCommands } from "@/features/workspace/commands"
import type { Support } from "@/features/workspace/commands"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppButton, AppTooltip } from "@/shared/ui"

/**
 * The bar at the foot of the screen: what can be done to the open connection.
 *
 * The room for it has been there since the workspace was built and has been
 * empty since. This is what it is for — a command that belongs to a connection
 * and to no node in it, which until now had to be squeezed in beside the plus
 * in the connections column.
 *
 * It also says which connection the commands are about. A row of buttons whose
 * subject is somewhere else on the screen is a row of buttons nobody trusts.
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
 * Whether this server could copy a database out, which is about the machine.
 *
 * The server answers with a reason when it cannot — no container runtime, or
 * nowhere to write what a dump produces — and the reason is what the button
 * says (D87).
 */
const offer = useBackupOffer()
const supportsBackups = computed<Support>(() => {
  if (workspace.activeConnectorId.value === null) return "no"
  if (offer.isLoading.value) return "asking"
  return offer.data.value?.available ? "yes" : "no"
})

const commands = computed(() =>
  connectionCommands({
    name: connector.value?.name ?? null,
    supportsQueries: supportsQueries.value,
    supportsBackups: supportsBackups.value,
    backupsRefusal: offer.data.value?.reason ?? undefined,
  })
)

/** The connection whose backups are being looked at, if any. */
const backingUp = ref<{ id: string; name: string } | null>(null)

function run(name: string) {
  if (name === "queries") workspace.openQueries(workspace.activeConnectorId.value)
  if (name === "backups" && connector.value) {
    backingUp.value = { id: connector.value.id, name: connector.value.name }
  }
}
</script>

<template>
  <div
    class="command-bar"
    data-testid="command-bar"
  >
    <span
      v-if="connector"
      class="command-bar__connection"
      data-testid="command-bar-connection"
    >
      <q-icon
        :name="adapterIcon(connector.adapter_type)"
        size="14px"
      />
      <span class="command-bar__name">{{ connector.name }}</span>
    </span>
    <span
      v-else
      class="command-bar__connection command-bar__connection--none"
      data-testid="command-bar-connection"
    >
      No connection open
    </span>

    <q-separator vertical />

    <!-- Greyed out rather than hidden, for the reason the catalog's menu is:
         a bar that changes shape as the user walks about is a bar they have to
         read every time. The tooltip is where the reason is. -->
    <span
      v-for="command in commands"
      :key="command.name"
      class="command-bar__slot"
    >
      <AppButton
        variant="quiet"
        size="sm"
        :icon="command.icon"
        :label="command.label"
        :disable="!command.enabled"
        :data-testid="`command-${command.name}`"
        @click="run(command.name)"
      />
      <AppTooltip>{{ command.tooltip }}</AppTooltip>
    </span>

    <BackupsDialog v-model:connector="backingUp" />
  </div>
</template>

<style scoped>
.command-bar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-width: 0;
}

.command-bar__connection {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 240px;
}

.command-bar__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.command-bar__connection--none {
  opacity: 0.6;
}

/* The tooltip hangs off this rather than off the button: a disabled Quasar
   button takes no pointer events, and the reason it is disabled is the one
   thing worth reading there. */
.command-bar__slot {
  display: flex;
  align-items: center;
}
</style>
