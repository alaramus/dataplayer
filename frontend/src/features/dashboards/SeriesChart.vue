<script setup lang="ts">
import { LineChart } from "echarts/charts"
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import type { EChartsType } from "echarts/core"
import { SVGRenderer } from "echarts/renderers"
import { onBeforeUnmount, onMounted, ref, watch } from "vue"

import { currentLanguage } from "@/shared/i18n"
import { useThemeStore } from "@/stores/theme"
import { chartLocale } from "@/shared/i18n/echarts"

import { timeseriesOption } from "./chartOption"
import type { ChartSeries } from "./chartOption"

use([LineChart, GridComponent, TooltipComponent, LegendComponent, SVGRenderer])

const props = defineProps<{ series: ChartSeries[] }>()

const theme = useThemeStore()
const host = ref<HTMLElement | null>(null)
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null

function colours(element: HTMLElement) {
  const style = getComputedStyle(element)
  const token = (name: string) => style.getPropertyValue(name).trim()
  return {
    palette: [1, 2, 3, 4, 5].map((index) => token(`--dp-chart-${String(index)}`)).filter(Boolean),
    text: token("--dp-text-muted"),
    grid: token("--dp-border-faint"),
    size: Number.parseFloat(token("--dp-font-size-xs")) || 11,
    font: token("--dp-font-ui"),
  }
}

function draw() {
  const element = host.value
  if (element === null || chart === null) return
  chart.setOption(timeseriesOption(props.series, colours(element)), true)
}

onMounted(() => {
  const element = host.value
  if (element === null) return
  chart = init(element, undefined, { renderer: "svg", locale: chartLocale() })
  draw()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

watch(() => props.series, draw, { deep: true })
// The palette is read off the theme, so a switch of theme is a redraw.
watch(() => theme.dark, () => requestAnimationFrame(draw))
// So are the unit words on the scale, which are the language's.
watch(currentLanguage, draw)
</script>

<template>
  <div
    ref="host"
    class="series-chart"
    data-testid="series-chart"
  />
</template>

<style scoped>
.series-chart {
  width: 100%;
  height: 100%;
  min-height: 0;
}
</style>
