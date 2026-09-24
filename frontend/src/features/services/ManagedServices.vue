<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { ServicePublic } from "@/client"
import ServiceCredentialsDialog from "@/features/services/ServiceCredentialsDialog.vue"
import ServiceLogsDialog from "@/features/services/ServiceLogsDialog.vue"
import {
  useCancelJob,
  useDeleteService,
  useRetryService,
  useServiceCommand,
  useServices,
} from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
import { lifecycleCommand } from "@/features/services/lifecycle"
import type { LifecycleCommand } from "@/features/services/lifecycle"
import { messageOf } from "@/shared/api/errors"
import {
  AppBadge,
  AppEmptyState,
  AppIconButton,
  AppSpinner,
  useConfirm,
  useToast,
} from "@/shared/ui"
import type { Tone } from "@/shared/ui"

/**
 * What this server is running. A service is the container a database lives in;
 * the connection beside it is how that database is used.
 *
 * The only place a service's life can be ended, taking the volume and
 * therefore the data with it. It is a tool of the panel at the foot of the
 * workspace rather than a strip above the connections: a service is looked at
 * while something is being done to it and not otherwise, and that column is
 * where every connection goes (D143).
 */
const services = useServices()
const removeService = useDeleteService()
const retryService = useRetryService()
const serviceCommand = useServiceCommand()
const cancelJob = useCancelJob()
const toast = useToast()
const reading = ref<ServicePublic | null>(null)
/** The service whose connection details are being shown, if any. */
const revealing = ref<{ id: string; name: string } | null>(null)

const rows = computed(() => services.data.value ?? [])

/**
 * What a service is doing, in the server's words.
 *
 * While something is happening, the step it has reached. Otherwise what this
 * application believes — and, when the runtime disagrees, both: a container
 * somebody removed by hand is the case the two exist to show (D84).
 */
function saying(service: ServicePublic): string {
  if (isWorking(service.job)) return progressOf(service.job)
  if (service.container_state === "missing") return `${service.state} · no container`
  if (service.container_state === "unknown") return service.state
  return service.container_state === service.state
    ? service.state
    : `${service.state} · ${service.container_state}`
}

function tone(service: ServicePublic): Tone {
  if (isWorking(service.job)) return "info"
  if (service.state === "failed") return "error"
  // A running container whose connection somebody deleted is not a green
  // thing: the database is fine and nothing in this application can reach it.
  if (service.connector_id === null && service.was_connected) return "warning"
  if (service.state === "running") return "success"
  return "warning"
}

/** What a person would say about when it was made. */
function madeOn(service: ServicePublic): string {
  return new Date(service.created_at).toLocaleString()
}

/**
 * A creation that did not finish can be made again, from the beginning.
 *
 * Asked of `was_connected` rather than of `connector_id`, which goes empty
 * again when somebody deletes the connection: that service is a database
 * still running, and retry starts by destroying what the earlier attempt left
 * (D84).
 */
function canRetry(service: ServicePublic): boolean {
  return !isWorking(service.job) && !service.was_connected
}

/** What the badge says about the connection this service made, if any. */
function connection(service: ServicePublic): string {
  if (service.connector_id !== null) return "connected"
  return service.was_connected ? "connection deleted" : "no connection yet"
}

async function retry(service: ServicePublic) {
  try {
    await retryService.mutateAsync(service.id)
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be started again"))
  }
}

const FAILURE: Record<LifecycleCommand, string> = {
  start: "It could not be started",
  stop: "It could not be stopped",
}

async function carryOut(service: ServicePublic, command: LifecycleCommand) {
  try {
    await serviceCommand.mutateAsync({ serviceId: service.id, command })
  } catch (cause) {
    toast.error(messageOf(cause, FAILURE[command]))
  }
}

/** Between the click and the job the list is read back with, for this row. */
function asking(service: ServicePublic): boolean {
  return (
    serviceCommand.isPending.value &&
    serviceCommand.variables.value?.serviceId === service.id
  )
}

async function cancel(service: ServicePublic) {
  if (!service.job) return
  try {
    await cancelJob.mutateAsync(service.job.id)
    toast.info("Cancelling")
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be cancelled"))
  }
}

const confirm = useConfirm()

/**
 * Taking a service away takes its data with it, so it is asked about first.
 *
 * And the connection it made is a second question in the same breath, ticked
 * by default: a connection to a database that no longer exists works for
 * nobody. Not decided here either way, because it may be shared and it may be
 * named in somebody's query history (D84) — so it is asked rather than
 * assumed, and a service that never became one is not asked about at all.
 */
async function forget(service: ServicePublic) {
  const name = service.connector_name
  let alsoTheConnection = service.connector_id !== null
  const sure = await confirm({
    title: "Remove this service?",
    message: `${name} and everything stored in it will be removed from this server.`,
    confirmLabel: "Remove",
    danger: true,
    alsoLabel:
      service.connector_id === null ? undefined : "Remove the connection as well",
    alsoDefault: true,
    onAlso: (chosen) => {
      alsoTheConnection = chosen
    },
  })
  if (!sure) return
  try {
    await removeService.mutateAsync({
      serviceId: service.id,
      deleteConnector: alsoTheConnection,
    })
  } catch {
    toast.error(`${name} could not be removed`)
  }
}
</script>

<template>
  <div
    class="starting"
    data-testid="managed-services"
  >
    <AppEmptyState
      v-if="rows.length === 0"
      icon="dns"
      text="This server is not running anything for you."
    />
    <div
      v-for="service in rows"
      :key="service.id"
      class="starting__row"
      :data-testid="`managed-service-${service.id}`"
    >
      <AppSpinner
        v-if="isWorking(service.job)"
        size="16px"
      />
      <q-icon
        v-else
        :name="service.state === 'failed' ? 'error' : 'dns'"
        size="16px"
        :class="service.state === 'failed' ? 'starting__failed' : ''"
      />
      <div class="starting__what">
        <span class="starting__name">{{ service.connector_name }}</span>
        <!-- Everything the server knows about it, which is the reason this is
             a panel of its own rather than a strip in a column: what it is,
             what runs it, and when it was made. -->
        <span class="starting__facts">
          {{ service.title }} · {{ service.container_name }} · {{ madeOn(service) }}
        </span>
        <!-- The server's own words for where it has got to: a step out of a
             list it declared, never a percentage this side invented. -->
        <span class="starting__step">{{ saying(service) }}</span>
      </div>
      <AppBadge
        :label="connection(service)"
        :tone="tone(service)"
      />
      <!-- Cancels the job, not the service, so it must not look like the stop
           that takes its place once the job is over. -->
      <AppIconButton
        v-if="isWorking(service.job)"
        :icon="appIcons.cancel"
        tooltip="Cancel what is happening"
        :data-testid="`cancel-service-${service.id}`"
        @click="cancel(service)"
      />
      <AppIconButton
        v-else-if="lifecycleCommand(service) === 'stop'"
        :icon="appIcons.stop"
        tooltip="Stop it; what is stored in it stays"
        :loading="asking(service)"
        :data-testid="`stop-service-${service.id}`"
        @click="carryOut(service, 'stop')"
      />
      <AppIconButton
        v-else-if="lifecycleCommand(service) === 'start'"
        :icon="appIcons.playArrow"
        tooltip="Start it"
        :loading="asking(service)"
        :data-testid="`start-service-${service.id}`"
        @click="carryOut(service, 'start')"
      />
      <AppIconButton
        v-if="canRetry(service)"
        :icon="appIcons.restartAlt"
        tooltip="Start over: the earlier attempt and its data are removed"
        :data-testid="`retry-service-${service.id}`"
        @click="retry(service)"
      />
      <!-- Offered for as long as the service exists: an address and the names
           it goes by are not a secret, so there is nothing to ration. Whatever
           was made up here is not in the answer (D89). -->
      <AppIconButton
        v-if="service.was_connected"
        :icon="appIcons.vpnKey"
        tooltip="Where it listens, for your own tools"
        :data-testid="`credentials-service-${service.id}`"
        @click="revealing = { id: service.id, name: service.connector_name }"
      />
      <AppIconButton
        :icon="appIcons.notes"
        tooltip="What it printed"
        :data-testid="`logs-service-${service.id}`"
        @click="reading = service"
      />
      <AppIconButton
        :icon="appIcons.deleteOutline"
        tooltip="Remove this service"
        variant="danger-quiet"
        :disable="isWorking(service.job)"
        :data-testid="`remove-service-${service.id}`"
        @click="forget(service)"
      />
    </div>

    <ServiceLogsDialog v-model:service="reading" />
    <!-- Without `reveal`: this one is opened whenever somebody asks, so it
         shows the address and the names and no secret at all (D89). -->
    <ServiceCredentialsDialog v-model:service="revealing" />
  </div>
</template>

<style scoped>
.starting {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 120px;
}
.starting__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) 0;
}
.starting__row + .starting__row {
  border-top: 1px solid var(--dp-border-faint);
}
.starting__what {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.starting__name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.starting__facts,
.starting__step {
  font-size: 11px;
  color: var(--dp-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.starting__failed {
  color: var(--dp-content-error);
}
</style>
