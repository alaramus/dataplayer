<script setup lang="ts">
import { BarChart, LineChart, PieChart } from "echarts/charts"
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import type { EChartsType } from "echarts/core"
import { SVGRenderer } from "echarts/renderers"
import type { EChartsOption } from "echarts"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

import type { FetchColumn } from "@/client"
import { useThemeStore } from "@/stores/theme"

import { buildChart } from "./model"
import type { ChartSpec } from "./types"

// D35's vocabulary, and only it: this panel composes the option itself, so
// what it can draw is what it offers to build.
use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, SVGRenderer])

const props = defineProps<{
  spec: ChartSpec
  columns: FetchColumn[]
  rows: Array<Array<string | null>>
  offset: number
}>()

const theme = useThemeStore()
const host = ref<HTMLElement | null>(null)
const built = computed(() => buildChart(props.spec, props.columns, props.rows, props.offset))
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null

function palette(element: HTMLElement): string[] {
  const style = getComputedStyle(element)
  return [1, 2, 3, 4, 5]
    .map((index) => style.getPropertyValue(`--dp-chart-${String(index)}`).trim())
    .filter((colour) => colour.length > 0)
}

/** The scale's caption size and face, for every word the chart draws (D187). */
function textStyle(element: HTMLElement): { fontFamily: string; fontSize: number } {
  const style = getComputedStyle(element)
  return {
    fontFamily: style.getPropertyValue("--dp-font-ui").trim(),
    fontSize: Number.parseFloat(style.getPropertyValue("--dp-font-size-xs")) || 11,
  }
}

function optionFor(element: HTMLElement, option: EChartsOption): EChartsOption {
  return {
    ...option,
    backgroundColor: "transparent",
    color: palette(element),
    textStyle: textStyle(element),
  }
}

function draw(): void {
  const element = host.value
  if (element === null || chart === null) return
  const answer = built.value
  if (answer === null) {
    chart.clear()
    return
  }
  chart.setOption(optionFor(element, answer.option), true)
}

function mountChart(): void {
  const element = host.value
  if (element === null) return
  chart?.dispose()
  chart = init(element, theme.dark ? "dark" : undefined, { renderer: "svg" })
  draw()
}

onMounted(() => {
  mountChart()
  if (typeof ResizeObserver !== "undefined" && host.value !== null) {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(host.value)
  }
})

watch(built, () => draw(), { deep: true })
watch(
  () => theme.dark,
  async () => {
    await nextTick()
    mountChart()
  }
)

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div class="chart-renderer">
    <div
      v-if="built === null"
      class="chart-renderer__empty"
      data-testid="chart-no-data"
    >
      No plottable values on this page
    </div>
    <div
      ref="host"
      class="chart-renderer__canvas"
      :class="{ 'chart-renderer__canvas--empty': built === null }"
      data-testid="chart-renderer"
    />
  </div>
</template>

<style scoped>
.chart-renderer {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 260px;
}

.chart-renderer__canvas {
  width: 100%;
  height: 100%;
}

.chart-renderer__canvas--empty {
  visibility: hidden;
}

.chart-renderer__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--dp-text-muted);
}
</style>
