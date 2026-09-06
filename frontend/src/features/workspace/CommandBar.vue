<script setup lang="ts">
import { computed, ref } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { useQueryProfile } from "@/features/queries/runs"
import ServicesDialog from "@/features/services/ServicesDialog.vue"
import { useServices } from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
import { queriesCommand, servicesCommand } from "@/features/workspace/commands"
import type { Support } from "@/features/workspace/commands"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppButton, AppTooltip } from "@/shared/ui"

/**
 * The bar at the foot of the screen: the library of queries and what this
 * server is running. What acts on the open connection is in the connection's
 * own menu, where the rest of what a connection can do already was.
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

const state = computed(() => ({
  name: connector.value?.name ?? null,
  supportsQueries: supportsQueries.value,
}))
/**
 * The library, which is the one thing in this row that is not the open
 * connection's: it is always pressable, and what it says depends on whether
 * there is a connection to open it against.
 */
const library = computed(() => queriesCommand(state.value))

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

function run(name: string) {
  if (name === "queries") workspace.openQueries(workspace.activeConnectorId.value)
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
