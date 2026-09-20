<script setup lang="ts">
import { computed } from "vue"

import { useServiceLogs } from "@/features/services/api"
import { AppEmptyState, AppSpinner } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * What a service printed, for when it did not do what it was asked.
 *
 * The container's own output and nothing else: this application's log is not
 * a user's to read, and the runtime's words about the machine are not either
 * (D84). A tail rather than a stream — the question is "why did it not
 * start", and that is answered by the last few hundred lines.
 */
const props = defineProps<{
  service: { id: string; connector_name: string } | null
}>()

const emit = defineEmits<{ "update:service": [value: null] }>()

const serviceId = computed(() => props.service?.id ?? null)
const logs = useServiceLogs(serviceId)
</script>

<template>
  <WindowDialog
    :model-value="service !== null"
    size="lg"
    :title="`Output of ${service?.connector_name ?? ''}`"
    subtitle="The last lines this service printed."
    data-testid="service-logs"
    @update:model-value="emit('update:service', null)"
  >
    <div class="service-logs">
      <AppSpinner v-if="logs.isLoading.value" />
      <AppEmptyState
        v-else-if="(logs.data.value?.lines.length ?? 0) === 0"
        icon="notes"
        text="It has printed nothing."
      />
      <pre
        v-else
        class="service-logs__text"
      >{{ logs.data.value?.lines.join("\n") }}</pre>
    </div>
  </WindowDialog>
</template>

<style scoped>
.service-logs {
  min-height: 200px;
  max-height: 60vh;
  overflow: auto;
}
.service-logs__text {
  margin: 0;
  font-family: var(--dp-font-mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
