<script setup lang="ts">
import { computed } from "vue"

import type { ConnectionCheckResult } from "@/client"

const props = defineProps<{
  result: ConnectionCheckResult | null
}>()

const KIND_LABELS: Record<string, string> = {
  auth: "Ошибка аутентификации",
  network: "Сервер недоступен",
  timeout: "Превышено время ожидания",
  config: "Ошибка в параметрах",
  unknown: "Неизвестная ошибка",
}

const text = computed(() => {
  if (!props.result) return ""
  if (props.result.ok) {
    return `${props.result.message} (${String(props.result.latency_ms)} мс)`
  }
  const kind = props.result.error_kind
  const prefix = kind ? KIND_LABELS[kind] : undefined
  return prefix ? `${prefix}: ${props.result.message}` : props.result.message
})
</script>

<template>
  <!-- Результат показывается строкой внутри диалога, а не уведомлением: его
       читают рядом с полями, которые правят. -->
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
