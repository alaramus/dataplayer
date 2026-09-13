<script setup lang="ts">
import { computed } from "vue"

import { messageOf } from "@/shared/api/errors"
import { AppSpinner } from "@/shared/ui"

import { useHistory } from "./api"
import { seriesName } from "./catalog"
import type { SeriesEntry } from "./catalog"
import type { ChartSeries } from "./chartOption"
import SeriesChart from "./SeriesChart.vue"

const props = defineProps<{
  seriesIds: number[]
  index: Map<number, SeriesEntry>
  rangeSeconds: number
  refreshSeconds: number
  dashboardId: string | null
}>()

const history = useHistory(
  () => props.seriesIds,
  () => props.rangeSeconds,
  () => props.refreshSeconds,
  600,
  () => props.dashboardId
)

const series = computed<ChartSeries[]>(() => {
  const entries = props.seriesIds.map((id) => props.index.get(id))
  const hosts = new Set(entries.map((entry) => entry?.host))
  const points = new Map((history.data.value?.series ?? []).map((one) => [one.series_id, one.points]))
  return props.seriesIds.map((id, position) => {
    const entry = entries[position]
    return {
      id,
      name: entry === undefined ? `series ${String(id)} (unavailable)` : seriesName(entry, hosts.size > 1),
      unit: entry?.unit ?? "",
      points: points.get(id) ?? [],
    }
  })
})

const failure = computed(() =>
  history.isError.value ? messageOf(history.error.value, "The history could not be read") : null
)
const empty = computed(
  () => history.isSuccess.value && series.value.every((one) => one.points.length === 0)
)

</script>

<template>
  <div class="timeseries-widget">
    <div
      v-if="failure"
      class="timeseries-widget__note"
    >
      {{ failure }}
    </div>
    <div
      v-else-if="history.isPending.value"
      class="timeseries-widget__note"
    >
      <AppSpinner />
    </div>
    <div
      v-else-if="empty"
      class="timeseries-widget__note"
    >
      Nothing reported in this range
    </div>
    <SeriesChart
      v-else
      :series="series"
    />
  </div>
</template>

<style scoped>
.timeseries-widget {
  width: 100%;
  height: 100%;
}

.timeseries-widget__note {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--dp-text-muted);
}
</style>
