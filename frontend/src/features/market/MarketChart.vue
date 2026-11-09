<script setup lang="ts">
import { BarChart, CandlestickChart } from "echarts/charts"
import { DataZoomComponent, GridComponent, TooltipComponent } from "echarts/components"
import { init, use } from "echarts/core"
import type { EChartsType } from "echarts/core"
import { SVGRenderer } from "echarts/renderers"
import { onBeforeUnmount, onMounted, ref, watch } from "vue"

import { chartLocale } from "@/shared/i18n/echarts"
import { currentLanguage } from "@/shared/i18n"
import { useThemeStore } from "@/stores/theme"

import type { ChartCandle } from "./model"

use([CandlestickChart, BarChart, GridComponent, TooltipComponent, DataZoomComponent, SVGRenderer])

/** A symbol's candles over its volume, the newest at the right (D323). */
const props = defineProps<{ candles: ChartCandle[] }>()

const theme = useThemeStore()
const host = ref<HTMLElement | null>(null)
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null
let drawing = 0

function colours(element: HTMLElement) {
  const style = getComputedStyle(element)
  const token = (name: string) => style.getPropertyValue(name).trim()
  return {
    up: token("--dp-content-success"),
    down: token("--dp-content-error"),
    text: token("--dp-text-muted"),
    grid: token("--dp-border-faint"),
    size: Number.parseFloat(token("--dp-font-size-xs")) || 11,
    font: token("--dp-font-ui"),
  }
}

function series() {
  return [
    { data: props.candles.map((one) => [one.time, one.open, one.close, one.low, one.high]) },
    {
      data: props.candles.map((one) => ({
        value: [one.time, one.volume],
        rising: one.close >= one.open,
      })),
    },
  ]
}

/** The whole option: on mounting and when the theme or the language changes. */
function drawAll() {
  const element = host.value
  if (element === null || chart === null) return
  const look = colours(element)
  const axisText = { color: look.text, fontSize: look.size, fontFamily: look.font }
  const [prices, volumes] = series()
  chart.setOption(
    {
      animation: false,
      textStyle: { fontFamily: look.font },
      grid: [
        { left: 8, right: 64, top: 8, bottom: "28%" },
        { left: 8, right: 64, top: "76%", bottom: 24 },
      ],
      xAxis: [
        { type: "time", gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: look.grid } } },
        {
          type: "time",
          gridIndex: 1,
          axisLabel: { ...axisText, hideOverlap: true },
          axisLine: { lineStyle: { color: look.grid } },
          splitNumber: 4,
        },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, position: "right", axisLabel: axisText, splitLine: { lineStyle: { color: look.grid } } },
        { scale: true, gridIndex: 1, position: "right", axisLabel: { show: false }, splitLine: { show: false } },
      ],
      dataZoom: [{ type: "inside", xAxisIndex: [0, 1], start: 60, end: 100 }],
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      series: [
        {
          type: "candlestick",
          xAxisIndex: 0,
          yAxisIndex: 0,
          encode: { x: 0, y: [1, 2, 3, 4] },
          itemStyle: { color: look.up, color0: look.down, borderColor: look.up, borderColor0: look.down },
          data: prices?.data,
        },
        {
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: {
            color: (params: { data: { rising: boolean } }) => (params.data.rising ? look.up : look.down),
          },
          data: volumes?.data,
        },
      ],
    },
    true
  )
}

/** New candles only: the zoom the person chose stays where they left it. */
function drawData() {
  if (chart === null) return
  cancelAnimationFrame(drawing)
  drawing = requestAnimationFrame(() => chart?.setOption({ series: series() }))
}

onMounted(() => {
  const element = host.value
  if (element === null) return
  chart = init(element, undefined, { renderer: "svg", locale: chartLocale() })
  drawAll()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(drawing)
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

watch(() => props.candles, drawData)
watch(() => theme.dark, () => requestAnimationFrame(drawAll))
watch(currentLanguage, drawAll)
</script>

<template>
  <div
    ref="host"
    class="market-chart"
    data-testid="market-chart"
  />
</template>

<style scoped>
.market-chart {
  width: 100%;
  height: 100%;
  min-height: 0;
}
</style>
