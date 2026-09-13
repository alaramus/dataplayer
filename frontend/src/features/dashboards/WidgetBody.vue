<script setup lang="ts">
import type { SeriesEntry } from "./catalog"
import type { ProcessLimit, ProcessSort, Widget } from "./dashboardModel"
import ProcessesWidget from "./ProcessesWidget.vue"
import StatWidget from "./StatWidget.vue"
import TimeseriesWidget from "./TimeseriesWidget.vue"

/** What a widget draws, by its type: on the dashboard and in a window alike. */
defineProps<{
  widget: Widget
  index: Map<number, SeriesEntry>
  rangeSeconds: number
  refreshSeconds: number
  dashboardId: string | null
}>()

const emit = defineEmits<{ options: [patch: { sort?: ProcessSort; limit?: ProcessLimit }] }>()
</script>

<template>
  <StatWidget
    v-if="widget.type === 'stat'"
    :series-id="widget.series_id"
    :index="index"
    :range-seconds="rangeSeconds"
    :refresh-seconds="refreshSeconds"
    :dashboard-id="dashboardId"
  />
  <ProcessesWidget
    v-else-if="widget.type === 'processes'"
    :agent-id="widget.agent_id"
    :host="widget.host"
    :sort="widget.sort ?? 'pcpu'"
    :limit="widget.limit ?? 20"
    :refresh-seconds="refreshSeconds"
    :dashboard-id="dashboardId"
    @options="(patch) => emit('options', patch)"
  />
  <TimeseriesWidget
    v-else
    :series-ids="widget.series_ids"
    :index="index"
    :range-seconds="rangeSeconds"
    :refresh-seconds="refreshSeconds"
    :dashboard-id="dashboardId"
  />
</template>
