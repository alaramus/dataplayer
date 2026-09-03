<script setup lang="ts">
import { computed, ref } from "vue"

import type { ServicePublic } from "@/client"
import ServiceCredentialsDialog from "@/features/services/ServiceCredentialsDialog.vue"
import ServiceLogsDialog from "@/features/services/ServiceLogsDialog.vue"
import {
  useCancelJob,
  useDeleteService,
  useRetryService,
  useServices,
} from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
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
 * What this server is running, and everything known about each one.
 *
 * A service is the container a database lives in; the connection beside it in
 * the column is how that database is used. Both are true of a ready service,
 * and this is the only place where its life can be ended — taking the volume,
 * and therefore the data, with it.
 *
 * This used to sit above the connections, in a column a fifth of the screen
 * wide that is also where every connection goes. A service is looked at while
 * something is being done to it and not otherwise, so it lives in a window
 * now and the bar at the foot of the screen says when there is one (D69).
 */
const services = useServices()
const removeService = useDeleteService()
const retryService = useRetryService()
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
  if (service.state === "running") return "success"
  return "warning"
}

/** What a person would say about when it was made. */
function madeOn(service: ServicePublic): string {
  return new Date(service.created_at).toLocaleString()
}

/** A creation that did not finish can be made again, from the beginning. */
function canRetry(service: ServicePublic): boolean {
  return !isWorking(service.job) && service.connector_id === null
}

async function retry(service: ServicePublic) {
  try {
    await retryService.mutateAsync(service.id)
    toast.info(`Starting ${service.connector_name} again`)
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be started again"))
  }
}

async function stop(service: ServicePublic) {
  if (!service.job) return
  try {
    await cancelJob.mutateAsync(service.job.id)
    toast.info("Stopping")
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be stopped"))
  }
}

const confirm = useConfirm()

/**
 * Taking a service away takes its data with it, so it is asked about first.
 *
 * The connection it made is left alone here: what happens to that is the
 * connector's own question, and answering it from this row would be this
 * screen deciding something the server has not been asked.
 */
async function forget(serviceId: string, name: string) {
  const sure = await confirm({
    title: "Remove this service?",
    message: `${name} and everything stored in it will be removed from this server.`,
    confirmLabel: "Remove",
    danger: true,
  })
  if (!sure) return
  try {
    await removeService.mutateAsync(serviceId)
    toast.info(`Removing ${name}`)
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
        :name="service.state === 'failed' ? 'error_outline' : 'dns'"
        size="16px"
        :class="service.state === 'failed' ? 'starting__failed' : ''"
      />
      <div class="starting__what">
        <span class="starting__name">{{ service.connector_name }}</span>
        <!-- Everything the server knows about it, which is the reason this is
             a window rather than a strip in a column: what it is, what runs
             it, and when it was made. -->
        <span class="starting__facts">
          {{ service.title }} · {{ service.container_name }} · {{ madeOn(service) }}
        </span>
        <!-- The server's own words for where it has got to: a step out of a
             list it declared, never a percentage this side invented. -->
        <span class="starting__step">{{ saying(service) }}</span>
      </div>
      <AppBadge
        :label="service.connector_id === null ? 'no connection yet' : 'connected'"
        :tone="tone(service)"
      />
      <AppIconButton
        v-if="isWorking(service.job)"
        icon="stop_circle"
        tooltip="Stop what is happening"
        :data-testid="`stop-service-${service.id}`"
        @click="stop(service)"
      />
      <AppIconButton
        v-if="canRetry(service)"
        icon="restart_alt"
        tooltip="Start over: the earlier attempt and its data are removed"
        :data-testid="`retry-service-${service.id}`"
        @click="retry(service)"
      />
      <!-- Offered until it has been taken: the password is shown once, and a
           button that would be refused is worse than no button (D82). -->
      <AppIconButton
        v-if="service.connector_id !== null && !service.credentials_shown"
        icon="vpn_key"
        tooltip="How to reach it from your own tools — shown once"
        :data-testid="`credentials-service-${service.id}`"
        @click="revealing = { id: service.id, name: service.connector_name }"
      />
      <AppIconButton
        icon="notes"
        tooltip="What it printed"
        :data-testid="`logs-service-${service.id}`"
        @click="reading = service"
      />
      <AppIconButton
        icon="delete_outline"
        tooltip="Remove this service"
        :disable="isWorking(service.job)"
        :data-testid="`remove-service-${service.id}`"
        @click="forget(service.id, service.connector_name)"
      />
    </div>

    <ServiceLogsDialog v-model:service="reading" />
    <ServiceCredentialsDialog v-model:service="revealing" />
  </div>
</template>

<style scoped>
.starting {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 120px;
}
.starting__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--dp-radius-control);
  background: var(--dp-surface-raised);
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
