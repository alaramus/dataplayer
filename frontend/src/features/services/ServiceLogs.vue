<script setup lang="ts">
import { toRef } from "vue"

import { useServiceLogs } from "@/features/services/api"
import { AppEmptyState, AppSpinner } from "@/shared/ui"

/**
 * What a service printed: the container's own output and nothing else (D84).
 * A tail rather than a stream — the question is "why did it not start", and
 * that is answered by the last few hundred lines. Drawn in a window and, once
 * it is moved, in a workspace tab (D155).
 */
const props = defineProps<{
  serviceId: string | null
}>()

const logs = useServiceLogs(toRef(props, "serviceId"))
</script>

<template>
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
</template>

<style scoped>
.service-logs {
  height: 100%;
  min-height: 200px;
  box-sizing: border-box;
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
