<script setup lang="ts">
import { computed } from "vue"

import type { ConnectionCheckResult } from "@/client"

const props = defineProps<{
  result: ConnectionCheckResult | null
}>()

const KIND_LABELS: Record<string, string> = {
  auth: "Authentication failed",
  network: "Server unreachable",
  timeout: "Timed out",
  config: "Invalid parameters",
  unknown: "Unknown error",
}

const text = computed(() => {
  if (!props.result) return ""
  if (props.result.ok) {
    return `${props.result.message} (${String(props.result.latency_ms)} ms)`
  }
  const kind = props.result.error_kind
  const prefix = kind ? KIND_LABELS[kind] : undefined
  return prefix ? `${prefix}: ${props.result.message}` : props.result.message
})
</script>

<template>
  <!-- The result is shown as a line inside the dialog rather than a toast: it
       is read next to the fields being edited. -->
  <q-banner
    v-if="result"
    dense
    class="text-white"
    :class="result.ok ? 'bg-positive' : 'bg-negative'"
    data-testid="check-result"
  >
    <template #avatar>
      <q-icon :name="result.ok ? 'check_circle' : 'error'" />
    </template>
    {{ text }}
  </q-banner>
</template>
