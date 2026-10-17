<script setup lang="ts">
import { computed } from "vue"

import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { formatDateTime } from "@/shared/i18n/format"
import { AppSpinner } from "@/shared/ui"

import { useHistory } from "./api"
import type { SeriesEntry } from "./catalog"
import { formatValue } from "./seriesFormat"
import { readStat } from "./statReading"

const props = defineProps<{
  seriesId: number
  index: Map<number, SeriesEntry>
  rangeSeconds: number
  refreshSeconds: number
  dashboardId: string | null
}>()

// Raw points, as many as the range holds: a fall inside the range is what a
// restart looks like, and a bucket's average would hide it.
const history = useHistory(
  () => [props.seriesId],
  () => props.rangeSeconds,
  () => props.refreshSeconds,
  5000,
  () => props.dashboardId
)

const unit = computed(() => props.index.get(props.seriesId)?.unit ?? "")
const reading = computed(() => {
  const points = history.data.value?.series[0]?.points ?? []
  return readStat(points, unit.value)
})
const failure = computed(() =>
  history.isError.value ? messageOf(history.error.value, t("dashboards.common.history_failed")) : null
)
</script>

<template>
  <div class="stat-widget">
    <span
      v-if="failure"
      class="stat-widget__note"
    >{{ failure }}</span>
    <AppSpinner v-else-if="history.isPending.value" />
    <span
      v-else-if="reading === null"
      class="stat-widget__note"
    >{{ t('dashboards.common.nothing_in_range') }}</span>
    <template v-else>
      <span
        class="stat-widget__value"
        data-testid="stat-value"
      >{{ formatValue(reading.value, unit) }}</span>
      <span
        v-if="reading.since !== null"
        class="stat-widget__note"
      >{{ t('dashboards.stat.since', { when: formatDateTime(reading.since * 1000) }) }}</span>
      <span
        v-if="reading.restarted"
        class="stat-widget__note"
      >{{ t('dashboards.stat.restarted') }}</span>
    </template>
  </div>
</template>

<style scoped>
.stat-widget {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--dp-space-1);
  height: 100%;
  text-align: center;
}

.stat-widget__value {
  font-size: var(--dp-font-size-display);
  line-height: var(--dp-line-height-page);
}
.stat-widget__note {
  color: var(--dp-text-muted);
}
</style>
