<script setup lang="ts">
import { computed, ref, toRef, watch } from "vue"

import type { FetchColumn, FetchRequest } from "@/client"
import { useRowsPage } from "@/features/grid/api"
import { useReloadable } from "@/features/workspace/reloadable"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppEmptyState, AppSelect, AppSpinner } from "@/shared/ui"

import ChartRenderer from "./ChartRenderer.vue"
import { isValidChartSpec, numericMeasureNames, suggestCharts } from "./model"
import { loadChartSpec, saveChartSpec } from "./persist"
import {
  ROW_FIELD,
  chartSpecKey,
  dimensionField,
  fieldLabel,
  makeChartSpec,
  measureField,
} from "./types"
import type { ChartSpec, ChartType } from "./types"

const props = defineProps<{
  panelId: string
  viewKey: string
  connectorId: string
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

useReloadable(props.panelId, async () => {
  refreshNext.value = true
  try {
    await rowsQuery.refetch()
  } finally {
    refreshNext.value = false
  }
})

const result = computed(() => rowsQuery.data.value)
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
const suggestions = computed(() =>
  suggestCharts(visibleColumns.value, rowsForVisibleColumns.value, offset.value)
)
const spec = ref<ChartSpec | null>(loadChartSpec(props.viewKey))

watch(
  [visibleColumns, suggestions],
  () => {
    if (
      spec.value !== null &&
      isValidChartSpec(spec.value, visibleColumns.value, rowsForVisibleColumns.value)
    ) {
      return
    }
    const stored = loadChartSpec(props.viewKey)
    spec.value =
      stored !== null && isValidChartSpec(stored, visibleColumns.value, rowsForVisibleColumns.value)
        ? stored
        : (suggestions.value[0]?.spec ?? null)
  },
  { immediate: true }
)
watch(
  spec,
  (next) => {
    if (next !== null) saveChartSpec(props.viewKey, next)
  },
  { deep: true }
)

const chartTypes = [
  { label: "Line", value: "line" },
  { label: "Bar", value: "bar" },
  { label: "Pie", value: "pie" },
] as const
const dimensionOptions = computed(() => [
  { label: "Row", value: ROW_FIELD },
  ...visibleColumns.value.map((column) => ({ label: column.name, value: column.name })),
])
const measureOptions = computed(() => {
  const names = numericMeasureNames(visibleColumns.value, rowsForVisibleColumns.value)
  return visibleColumns.value
    .filter((column) => names.has(column.name))
    .map((column) => ({
      label:
        column.type.category === "number" ? column.name : `${column.name} (numeric on this page)`,
      value: column.name,
    }))
})
const suggestionOptions = computed(() =>
  suggestions.value.map((suggestion) => ({
    label: suggestion.label,
    value: chartSpecKey(suggestion.spec),
  }))
)
const selectedSuggestion = computed(() => (spec.value === null ? "" : chartSpecKey(spec.value)))

function setType(value: unknown): void {
  if (value !== "line" && value !== "bar" && value !== "pie") return
  const type: ChartType = value
  const suggested = suggestions.value.find((suggestion) => suggestion.spec.type === type)
  if (suggested !== undefined) {
    spec.value = suggested.spec
    return
  }
  const measure = spec.value === null ? measureOptions.value[0]?.value : measureField(spec.value)
  const dimension = spec.value === null ? ROW_FIELD : dimensionField(spec.value)
  if (measure !== undefined) spec.value = makeChartSpec(type, dimension, String(measure))
}

function setDimension(value: unknown): void {
  if (typeof value !== "string" || spec.value === null) return
  spec.value = makeChartSpec(spec.value.type, value, measureField(spec.value))
}

function setMeasure(value: unknown): void {
  if (typeof value !== "string" || spec.value === null) return
  spec.value = makeChartSpec(spec.value.type, dimensionField(spec.value), value)
}

function chooseSuggestion(value: unknown): void {
  if (typeof value !== "string") return
  const selected = suggestions.value.find(
    ({ spec: candidate }) => chartSpecKey(candidate) === value
  )
  if (selected !== undefined) spec.value = selected.spec
}

const pageLabel = computed(() => {
  const count = result.value?.rows.length ?? 0
  if (count === 0) return "Current page · Rows 0"
  return `Current page · Rows ${String(offset.value + 1)}–${String(offset.value + count)}`
})
</script>

<template>
  <div class="chart-panel" data-testid="chart-panel">
    <AppBanner
      v-if="rowsQuery.isError.value"
      tone="error"
      class="chart-panel__message"
      data-testid="chart-error"
    >
      {{ messageOf(rowsQuery.error.value, "Could not read the chart page") }}
    </AppBanner>

    <div v-else-if="rowsQuery.isPending.value" class="chart-panel__loading">
      <AppSpinner />
    </div>

    <template v-else>
      <div class="chart-panel__notice">
        <strong>{{ pageLabel }}</strong>
        <span v-if="result?.has_more">Later rows are not included.</span>
        <span v-else>The chart uses only this bounded result.</span>
      </div>

      <AppEmptyState
        v-if="measureOptions.length === 0"
        text="This page has no numeric visible column to chart"
        data-testid="chart-no-measure"
      />

      <div v-else-if="spec !== null" class="chart-panel__body">
        <aside class="chart-panel__controls">
          <AppSelect
            :model-value="selectedSuggestion"
            :options="suggestionOptions"
            label="Suggested view"
            data-testid="chart-suggestion"
            @update:model-value="chooseSuggestion"
          />
          <AppSelect
            :model-value="spec.type"
            :options="chartTypes"
            label="Chart type"
            data-testid="chart-type"
            @update:model-value="setType"
          />
          <AppSelect
            :model-value="dimensionField(spec)"
            :options="dimensionOptions"
            :label="spec.type === 'pie' ? 'Label' : 'X axis'"
            data-testid="chart-dimension"
            @update:model-value="setDimension"
          />
          <AppSelect
            :model-value="measureField(spec)"
            :options="measureOptions"
            :label="spec.type === 'pie' ? 'Value' : 'Y axis'"
            data-testid="chart-measure"
            @update:model-value="setMeasure"
          />
          <AppButton
            label="Best fit"
            variant="secondary"
            size="sm"
            :disable="suggestions.length === 0"
            data-testid="chart-best-fit"
            @click="spec = suggestions[0]?.spec ?? spec"
          />
          <p class="chart-panel__selection">
            {{ fieldLabel(dimensionField(spec)) }} → {{ measureField(spec) }}
          </p>
        </aside>

        <main class="chart-panel__chart">
          <ChartRenderer
            :spec="spec"
            :columns="visibleColumns"
            :rows="rowsForVisibleColumns"
            :offset="offset"
          />
        </main>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chart-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
}

.chart-panel__message {
  margin: 12px;
}

.chart-panel__loading {
  display: grid;
  flex: 1;
  place-items: center;
}

.chart-panel__notice {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
  min-height: 36px;
  padding: 4px 10px;
  border-bottom: 1px solid var(--dp-border);
  color: var(--dp-text-muted);
  font-size: 12px;
}

.chart-panel__body {
  display: grid;
  grid-template-columns: minmax(180px, 240px) minmax(300px, 1fr);
  flex: 1;
  min-height: 0;
}

.chart-panel__controls {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  padding: 12px 10px;
  overflow-y: auto;
  border-right: 1px solid var(--dp-border);
}

.chart-panel__chart {
  min-width: 0;
  min-height: 0;
  padding: 8px;
}

.chart-panel__selection {
  margin: 0;
  color: var(--dp-text-faint);
  font-size: 12px;
}

@media (max-width: 720px) {
  .chart-panel__body {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(280px, 1fr);
    overflow-y: auto;
  }

  .chart-panel__controls {
    display: grid;
    grid-template-columns: repeat(2, minmax(140px, 1fr));
    border-right: 0;
    border-bottom: 1px solid var(--dp-border);
  }
}
</style>
