<script setup lang="ts">
import type { Panel } from "@/features/workspace/panels"

import type { RangeSeconds, RefreshSeconds } from "./dashboardModel"
import WidgetWindow from "./WidgetWindow.vue"

/**
 * A dashboard widget as a workspace tab (D155). The same view the floating
 * window holds, over the same copy taken when the window was opened: a tab is
 * where the window's contents went, not a second read of the dashboard.
 */
defineProps<{
  panelId: string
  panel: Extract<Panel, { kind: "widget" }>
}>()
</script>

<template>
  <WidgetWindow
    :widget="panel.widget"
    :range-seconds="panel.rangeSeconds as RangeSeconds"
    :refresh-seconds="panel.refreshSeconds as RefreshSeconds"
    :dashboard-id="panel.dashboardId"
  />
</template>
