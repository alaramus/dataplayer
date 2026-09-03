<script setup lang="ts">
import { computed } from "vue"

import type { JobPublic } from "@/client"
import { useDeleteService, useServices } from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
import { AppIconButton, AppSpinner, useConfirm, useToast } from "@/shared/ui"

/**
 * What this server is running, above the connections it is used through.
 *
 * Both, and not one: the connection is how a database is used, and the
 * service is the container it lives in — one is opened and read, the other is
 * started, stopped and taken away with its data. A ready service appears in
 * both places because both statements are true of it, and the row here is the
 * only place its life can be ended.
 */
const services = useServices()
const removeService = useDeleteService()
const toast = useToast()

const rows = computed(() => services.data.value ?? [])

/** What a service is doing, in the server's words: a step, or a state. */
function saying(service: { state: string; job?: JobPublic | null }): string {
  return isWorking(service.job) ? progressOf(service.job) : service.state
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
    v-if="rows.length > 0"
    class="starting"
    data-testid="managed-services"
  >
    <div class="starting__heading">
      Started here
    </div>
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
        <!-- The server's own words for where it has got to: a step out of a
             list it declared, never a percentage this side invented. -->
        <span class="starting__step">{{ saying(service) }}</span>
      </div>
      <AppIconButton
        icon="delete_outline"
        tooltip="Remove this service"
        :disable="isWorking(service.job)"
        :data-testid="`remove-service-${service.id}`"
        @click="forget(service.id, service.connector_name)"
      />
    </div>
  </div>
</template>

<style scoped>
.starting__heading {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--dp-text-faint);
  padding: 2px 6px;
}
.starting {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 4px 6px;
}
.starting__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
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
