<script setup lang="ts">
import { computed, inject } from "vue"

import ServiceLogs from "@/features/services/ServiceLogs.vue"
import { workspaceActionsKey } from "@/features/workspace/state"
import { t } from "@/shared/i18n"
import { openAsTabAction, WindowDialog } from "@/shared/windows"

/**
 * What a service printed, for when it did not do what it was asked.
 *
 * The dialog's contents can live as a workspace tab instead, so the window
 * says so (D155): pressing the command opens the tab and closes the window —
 * a move, not a copy. Outside a workspace there is nowhere to move to, and the
 * command is absent rather than inert.
 */
const props = defineProps<{
  service: { id: string; connector_name: string } | null
}>()

const emit = defineEmits<{ "update:service": [value: null] }>()

const workspace = inject(workspaceActionsKey, null)

const serviceId = computed(() => props.service?.id ?? null)

const actions = computed(() => {
  const service = props.service
  if (service === null || workspace === null) return undefined
  return [
    openAsTabAction(() => {
      workspace.openServiceLogsTab({ serviceId: service.id, serviceName: service.connector_name })
      emit("update:service", null)
    }),
  ]
})
</script>

<template>
  <WindowDialog
    :model-value="service !== null"
    size="wide-form"
    sizing="stable"
    :title="t('services.logs.title', { name: service?.connector_name ?? '' })"
    :actions="actions"
    data-testid="service-logs"
    @update:model-value="emit('update:service', null)"
  >
    <ServiceLogs
      class="service-logs-dialog__logs"
      :service-id="serviceId"
    />
  </WindowDialog>
</template>
