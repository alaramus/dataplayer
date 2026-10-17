<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, nextTick, ref, watch } from "vue"

import type { ServicePublic } from "@/client"
import { useFadingMark } from "@/features/catalog/fadingMark"
import { pointedService, takePointedService } from "@/features/services/pointed"
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
import { t } from "@/shared/i18n"
import { formatDateTime } from "@/shared/i18n/format"
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
 * The service the search found (D205): scrolled to and marked for a moment,
 * as a catalog marks a row it was asked to show. Waits for the list, and says
 * so when the service is not on it.
 */
const { value: pointed, show: point } = useFadingMark<string>(3000)
watch(
  [pointedService, () => services.data.value],
  async ([id, listed]) => {
    if (id === null || listed === undefined) return
    takePointedService()
    if (!listed.some((row) => row.id === id)) {
      toast.info(t("services.managed.gone"))
      return
    }
    point(id)
    await nextTick()
    document.querySelector(`[data-service-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest" })
  },
  { immediate: true }
)

/**
 * What a service is doing, in the server's words.
 *
 * While something is happening, the step it has reached. Otherwise what this
 * application believes — and, when the runtime disagrees, both: a container
 * somebody removed by hand is the case the two exist to show (D84).
 */
function saying(service: ServicePublic): string {
  if (isWorking(service.job)) return progressOf(service.job)
  const state = t(`services.managed.states.${service.state}`)
  if (service.container_state === "missing") return t("services.managed.no_container", { state })
  if (service.container_state === "unknown") return state
  return service.container_state === service.state
    ? state
    : t("services.managed.both", {
      state, container: t(`services.managed.container_states.${service.container_state}`),
    })
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
  return formatDateTime(service.created_at)
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
  if (service.connector_id !== null) return t("services.managed.connected")
  return t(service.was_connected ? "services.managed.connection_deleted" : "services.managed.no_connection")
}

async function retry(service: ServicePublic) {
  try {
    await retryService.mutateAsync(service.id)
  } catch (cause) {
    toast.error(messageOf(cause, t("services.managed.retry_failed")))
  }
}


async function carryOut(service: ServicePublic, command: LifecycleCommand) {
  try {
    await serviceCommand.mutateAsync({ serviceId: service.id, command })
  } catch (cause) {
    toast.error(messageOf(cause, t(command === "start" ? "services.managed.start_failed" : "services.managed.stop_failed")))
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
    toast.info(t("services.managed.cancelling"))
  } catch (cause) {
    toast.error(messageOf(cause, t("services.managed.cancel_failed")))
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
    title: t("services.managed.remove_title"),
    message: t("services.managed.remove_message", { name }),
    confirmLabel: t("services.managed.remove"),
    danger: true,
    alsoLabel:
      service.connector_id === null ? undefined : t("services.managed.remove_connection"),
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
    toast.error(t("services.managed.remove_failed", { name }))
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
      :text="t('services.managed.empty')"
      inset
    />
    <div
      v-for="service in rows"
      :key="service.id"
      class="starting__row"
      :class="{ 'starting__row--pointed': service.id === pointed }"
      :data-service-id="service.id"
      :aria-current="service.id === pointed ? 'true' : undefined"
      :data-testid="`managed-service-${service.id}`"
    >
      <AppSpinner
        v-if="isWorking(service.job)"
        size="var(--dp-icon-sm)"
      />
      <q-icon
        v-else
        :name="service.state === 'failed' ? 'error' : 'dns'"
        size="var(--dp-icon-sm)"
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
        :tooltip="t('services.managed.cancel_job')"
        :data-testid="`cancel-service-${service.id}`"
        @click="cancel(service)"
      />
      <AppIconButton
        v-else-if="lifecycleCommand(service) === 'stop'"
        :icon="appIcons.stop"
        :tooltip="t('services.managed.stop')"
        :loading="asking(service)"
        :data-testid="`stop-service-${service.id}`"
        @click="carryOut(service, 'stop')"
      />
      <AppIconButton
        v-else-if="lifecycleCommand(service) === 'start'"
        :icon="appIcons.playArrow"
        :tooltip="t('services.managed.start')"
        :loading="asking(service)"
        :data-testid="`start-service-${service.id}`"
        @click="carryOut(service, 'start')"
      />
      <AppIconButton
        v-if="canRetry(service)"
        :icon="appIcons.restartAlt"
        :tooltip="t('services.managed.retry')"
        :data-testid="`retry-service-${service.id}`"
        @click="retry(service)"
      />
      <!-- Offered for as long as the service exists: an address and the names
           it goes by are not a secret, so there is nothing to ration. Whatever
           was made up here is not in the answer (D89). -->
      <AppIconButton
        v-if="service.was_connected"
        :icon="appIcons.vpnKey"
        :tooltip="t('services.managed.credentials')"
        :data-testid="`credentials-service-${service.id}`"
        @click="revealing = { id: service.id, name: service.connector_name }"
      />
      <AppIconButton
        :icon="appIcons.notes"
        :tooltip="t('services.managed.logs')"
        :data-testid="`logs-service-${service.id}`"
        @click="reading = service"
      />
      <AppIconButton
        :icon="appIcons.deleteOutline"
        :tooltip="t('services.managed.remove_tooltip')"
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
  padding-right: var(--dp-space-2);
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
.starting__row--pointed {
  background: var(--dp-selected-quiet);
}
.starting__what {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.starting__name {
  font-size: var(--dp-font-size);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.starting__facts,
.starting__step {
  font-size: var(--dp-font-size-xs);
  color: var(--dp-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.starting__failed {
  color: var(--dp-content-error);
}
</style>
