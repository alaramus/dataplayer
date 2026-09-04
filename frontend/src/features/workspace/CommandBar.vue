<script setup lang="ts">
import { computed, ref } from "vue"

import { useAdapterTypes, useConnectors } from "@/features/connectors/api"
import { useQueryProfile } from "@/features/queries/runs"
import BackupsDialog from "@/features/services/BackupsDialog.vue"
import ServicesDialog from "@/features/services/ServicesDialog.vue"
import { useBackupOffer, useServices } from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
import {
  connectionCommands,
  queriesCommand,
  servicesCommand,
} from "@/features/workspace/commands"
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
 * Which connection they are about is not written here. It is said twice
 * already, in the column of connections and on the tab of the catalog being
 * read, and a third copy at the foot of the screen only took the room the
 * commands themselves want; each tooltip names the connection, so the answer
 * is still a hover away where a button leaves any doubt (D69).
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
 * Whether this connection could be copied out, which is two questions.
 *
 * The machine is one: the server answers with a reason when it cannot — no
 * container runtime, or nowhere to write what a dump produces (D87). The
 * source is the other, and it is read where every other capability is read,
 * off the type: a driver that can name a program to dump it declares
 * `backup`, and a file source and a Redis server do not (D2).
 *
 * A button offered on a connection that would be refused is the thing this
 * exists to stop, so the refusal names whichever of the two said no.
 */
const offer = useBackupOffer()
const adapterTypes = useAdapterTypes()

const sourceCanBackUp = computed<Support>(() => {
  const adapterType = connector.value?.adapter_type
  if (adapterType === undefined) return "no"
  if (adapterTypes.data.value === undefined) return "asking"
  return (adapterTypes.data.value.find((type) => type.name === adapterType)
    ?.capabilities.some((capability) => capability.code === "backup") ?? false)
    ? "yes"
    : "no"
})

const supportsBackups = computed<Support>(() => {
  if (workspace.activeConnectorId.value === null) return "no"
  if (sourceCanBackUp.value !== "yes") return sourceCanBackUp.value
  if (offer.isLoading.value) return "asking"
  return offer.data.value?.available ? "yes" : "no"
})

const backupsRefusal = computed(() =>
  sourceCanBackUp.value === "no"
    ? "This kind of connection cannot be copied out"
    : (offer.data.value?.reason ?? undefined)
)

const state = computed(() => ({
  name: connector.value?.name ?? null,
  supportsQueries: supportsQueries.value,
  supportsBackups: supportsBackups.value,
  backupsRefusal: backupsRefusal.value,
}))
/**
 * The library, which is the one thing in this row that is not the open
 * connection's: it is always pressable, and what it says depends on whether
 * there is a connection to open it against.
 */
const library = computed(() => queriesCommand(state.value))
const commands = computed(() => connectionCommands(state.value))

/**
 * What this server is running for this person, which is not about a
 * connection at all.
 *
 * So it stands apart from the rest of the bar rather than among them. While a
 * job is working the button says the step it has reached: once the dialog
 * that asked for a service has closed, this is the only place a start is
 * visible (D81).
 */
const services = useServices()
const working = computed(() => {
  const busy = (services.data.value ?? []).find((row) => isWorking(row.job))
  return busy === undefined ? null : `${busy.connector_name}: ${progressOf(busy.job)}`
})
const serviceCommand = computed(() =>
  servicesCommand({ count: (services.data.value ?? []).length, working: working.value })
)
const servicesOpen = ref(false)

/** The connection whose backups are being looked at, if any. */
const backingUp = ref<{ id: string; name: string } | null>(null)

function run(name: string) {
  if (name === "queries") workspace.openQueries(workspace.activeConnectorId.value)
  if (name === "backups" && connector.value) {
    backingUp.value = { id: connector.value.id, name: connector.value.name }
  }
  if (name === "services") servicesOpen.value = true
}
</script>

<template>
  <div
    class="command-bar"
    data-testid="command-bar"
  >
    <!-- First, and never greyed out: what a person has written is theirs
         whether or not a connection is open. -->
    <span class="command-bar__slot">
      <AppButton
        variant="quiet"
        size="sm"
        :icon="library.icon"
        :label="library.label"
        data-testid="command-queries"
        @click="run('queries')"
      />
      <AppTooltip>{{ library.tooltip }}</AppTooltip>
    </span>

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

    <!-- On the right, away from the commands of the open connection: this one
         is about the machine, and a button whose subject is different from
         its neighbours' should not sit in the same row of them. -->
    <span class="command-bar__slot command-bar__aside">
      <AppButton
        variant="quiet"
        size="sm"
        :icon="serviceCommand.icon"
        :label="serviceCommand.label"
        :disable="!serviceCommand.enabled"
        data-testid="command-services"
        @click="run('services')"
      />
      <AppTooltip>{{ serviceCommand.tooltip }}</AppTooltip>
    </span>

    <BackupsDialog v-model:connector="backingUp" />
    <ServicesDialog v-model="servicesOpen" />
  </div>
</template>

<style scoped>
.command-bar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-width: 0;
  /* The bar is the whole width of the footer, so that what is about the
     machine can sit at the far end of it. */
  flex: 1;
}

.command-bar__aside {
  margin-left: auto;
}

/* The tooltip hangs off this rather than off the button: a disabled Quasar
   button takes no pointer events, and the reason it is disabled is the one
   thing worth reading there. */
.command-bar__slot {
  display: flex;
  align-items: center;
}
</style>
