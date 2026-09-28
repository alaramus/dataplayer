<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { FetchColumn } from "@/client"
import { AppButton, AppEmptyState, AppSelect } from "@/shared/ui"

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

/**
 * Choosing a chart over rows somebody else read (D35).
 *
 * Controlled, like the tabular surface of D24: it is given columns, rows and
 * where they start, and knows nothing about where they came from. A relation's
 * page and a captured query result are two controllers of the same thing, and
 * this is what keeps the pickers, the suggestions and the persistence in one
 * place rather than in two that drift.
 */

const props = defineProps<{
  /** Where this chart's choice is remembered, per view. */
  viewKey: string
  columns: FetchColumn[]
  rows: (string | null)[][]
  /** The ordinal of the first row, so "Row" means the same as on screen. */
  offset: number
}>()

const suggestions = computed(() => suggestCharts(props.columns, props.rows, props.offset))
const spec = ref<ChartSpec | null>(loadChartSpec(props.viewKey))

watch(
  [() => props.columns, suggestions] as const,
  () => {
    if (spec.value !== null && isValidChartSpec(spec.value, props.columns, props.rows)) {
      return
    }
    const stored = loadChartSpec(props.viewKey)
    spec.value =
      stored !== null && isValidChartSpec(stored, props.columns, props.rows)
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
  ...props.columns.map((column) => ({ label: column.name, value: column.name })),
])
const measureOptions = computed(() => {
  const names = numericMeasureNames(props.columns, props.rows)
  return props.columns
    .filter((column) => names.has(column.name))
    .map((column) => ({
      label:
        column.type.category === "number"
          ? column.name
          : `${column.name} (numeric on this page)`,
      value: column.name,
    }))
})
const suggestionOptions = computed(() =>
  suggestions.value.map((suggestion) => ({
    label: suggestion.label,
    value: chartSpecKey(suggestion.spec),
  }))
)
const selectedSuggestion = computed(() =>
  spec.value === null ? "" : chartSpecKey(spec.value)
)

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
</script>

<template>
  <AppEmptyState
    v-if="measureOptions.length === 0"
    text="This page has no numeric visible column to chart"
    data-testid="chart-no-measure"
  />

  <div
    v-else-if="spec !== null"
    class="chart-view"
  >
    <aside class="chart-view__controls">
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
      <p class="chart-view__selection">
        {{ fieldLabel(dimensionField(spec)) }} → {{ measureField(spec) }}
      </p>
    </aside>

    <main class="chart-view__chart">
      <ChartRenderer
        :spec="spec"
        :columns="columns"
        :rows="rows"
        :offset="offset"
      />
    </main>
  </div>
</template>

<style scoped>
.chart-view {
  display: grid;
  grid-template-columns: minmax(180px, 240px) minmax(300px, 1fr);
  flex: 1;
  min-height: 0;
}

.chart-view__controls {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-height: 0;
  padding: var(--dp-space-3) var(--dp-space-2);
  overflow-y: auto;
  border-right: 1px solid var(--dp-border);
}

.chart-view__chart {
  min-width: 0;
  min-height: 0;
  padding: var(--dp-space-2);
}

.chart-view__selection {
  margin: 0;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}

@media (max-width: 720px) {
  .chart-view {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(280px, 1fr);
    overflow-y: auto;
  }

  .chart-view__controls {
    display: grid;
    grid-template-columns: repeat(2, minmax(140px, 1fr));
    border-right: 0;
    border-bottom: 1px solid var(--dp-border);
  }
}
</style>
