<script setup lang="ts">
import { computed, ref, toRef } from "vue"

import type { FetchColumn, FetchRequest } from "@/client"
import { useRowsPage } from "@/features/grid/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppSpinner } from "@/shared/ui"

import ChartView from "./ChartView.vue"

/**
 * A chart of one relation's visible page (D35).
 *
 * The controller: it reads the page the grid was showing and hands the rows to
 * the controlled chart. What may be charted, and how, is that component's
 * business — a captured query result asks it exactly the same thing.
 */

const props = defineProps<{
  panelId: string
  viewKey: string
  connectorId: string
  title: string
  request: FetchRequest
  columns: string[]
}>()

const refreshNext = ref(false)
const request = computed(() => props.request)
const rowsQuery = useRowsPage(toRef(props, "connectorId"), request, () => {
  const wanted = refreshNext.value
  refreshNext.value = false
  return wanted
})

useReloadable(() => props.panelId, async () => {
  refreshNext.value = true
  try {
    await rowsQuery.refetch()
  } finally {
    refreshNext.value = false
  }
})

const result = computed(() => rowsQuery.data.value?.page)
const visibleColumns = computed<FetchColumn[]>(() => {
  const answer = result.value
  if (answer === undefined) return []
  const byName = new Map(answer.columns.map((column) => [column.name, column]))
  return props.columns.flatMap((name) => {
    const column = byName.get(name)
    return column === undefined ? [] : [column]
  })
})
const rowsForVisibleColumns = computed<Array<Array<string | null>>>(() => {
  const answer = result.value
  if (answer === undefined) return []
  const indexes = visibleColumns.value.map((column) =>
    answer.columns.findIndex((candidate) => candidate.name === column.name)
  )
  return answer.rows.map((row) => indexes.map((index) => row[index] ?? null))
})
const offset = computed(() => props.request.offset ?? 0)

const pageLabel = computed(() => {
  const count = result.value?.rows.length ?? 0
  if (count === 0) return t("charts.page.none")
  return t("charts.page.range", { first: offset.value + 1, last: offset.value + count })
})
</script>

<template>
  <div
    class="chart-panel"
    data-testid="chart-panel"
  >
    <!-- No way back to a catalog: a chart is drawn from a page of rows and
         is not a view of a node, so it offers no button rather than one that
         does nothing (D112). -->
    <div class="chart-panel__bar">
      <span class="chart-panel__title">{{ title }}</span>
      <div
        v-if="result"
        class="chart-panel__notice"
      >
        <strong>{{ pageLabel }}</strong>
        <span v-if="result?.has_more">{{ t("charts.page.more") }}</span>
        <span v-else>{{ t("charts.page.bounded") }}</span>
      </div>
      <PanelCommands :panel-id="panelId" />
    </div>

    <SourceErrorBanner
      v-if="rowsQuery.isError.value"
      class="chart-panel__message"
      :connector-id="connectorId"
      :error-kind="errorKindOf(rowsQuery.error.value)"
      data-testid="chart-error"
    >
      {{ messageOf(rowsQuery.error.value, t("charts.read_failed")) }}
    </SourceErrorBanner>

    <div
      v-else-if="rowsQuery.isPending.value"
      class="chart-panel__loading"
    >
      <AppSpinner />
    </div>

    <template v-else>
      <ChartView
        :view-key="viewKey"
        :columns="visibleColumns"
        :rows="rowsForVisibleColumns"
        :offset="offset"
      />
    </template>
  </div>
</template>

<style scoped>
.chart-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}

.chart-panel__bar {
  display: flex;
  align-items: center;
  flex: none;
  gap: var(--dp-space-2);
  min-height: 36px;
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border);
}

.chart-panel__title {
  flex: 0 1 var(--dp-width-name);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.chart-panel__message {
  margin: var(--dp-space-3);
}

.chart-panel__loading {
  display: grid;
  flex: 1;
  place-items: center;
}

.chart-panel__notice {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: var(--dp-space-2);
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  white-space: nowrap;
}

.chart-panel__notice strong {
  flex: none;
}

.chart-panel__notice span {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
