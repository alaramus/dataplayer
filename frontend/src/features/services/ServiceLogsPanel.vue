<script setup lang="ts">
import type { Panel } from "@/features/workspace/panels"

import ServiceLogs from "./ServiceLogs.vue"

/**
 * A service's output as a workspace tab (D155): the dialog's contents moved,
 * read again whenever the tab is shown.
 */
defineProps<{
  panelId: string
  panel: Extract<Panel, { kind: "service-logs" }>
}>()
</script>

<template>
  <ServiceLogs :service-id="panel.serviceId" />
</template>
