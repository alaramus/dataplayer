<script setup lang="ts">
import { computed, ref } from "vue"

import { useDashboardCatalog, useLivePoints, useMetricsCatalog } from "./api"
import { indexCatalog } from "./catalog"
import { mergedIndex } from "./sharing"
import type { ProcessLimit, ProcessSort, RangeSeconds, RefreshSeconds, Widget } from "./dashboardModel"
import { withOptions } from "./dashboardModel"
import WidgetBody from "./WidgetBody.vue"

/**
 * One widget in a floating window, over whichever space is shown.
 *
 * A copy taken when it was opened: moving or removing it on the dashboard does
 * not reach the window, and a sort chosen here is not saved there.
 */
const props = defineProps<{
  widget: Widget
  rangeSeconds: RangeSeconds
  refreshSeconds: RefreshSeconds
  dashboardId: string
}>()

useLivePoints()
const catalog = useMetricsCatalog(true)
const throughDashboard = useDashboardCatalog(() => props.dashboardId)
const index = computed(() =>
  mergedIndex(indexCatalog(catalog.data.value), indexCatalog(throughDashboard.data.value))
)
const shown = ref<Widget>(props.widget)

function applyOptions(patch: { sort?: ProcessSort; limit?: ProcessLimit }) {
  shown.value = withOptions([shown.value], shown.value.id, patch)[0] ?? shown.value
}
</script>

<template>
  <div
    class="widget-window"
    data-testid="widget-window"
  >
    <WidgetBody
      :widget="shown"
      :index="index"
      :range-seconds="rangeSeconds"
      :refresh-seconds="refreshSeconds"
      :dashboard-id="dashboardId"
      @options="applyOptions"
    />
  </div>
</template>

<style scoped>
.widget-window {
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  padding: var(--dp-space-2);
}
</style>
