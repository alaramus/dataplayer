<script setup lang="ts">
import { appIcons } from "@/shared/ui"
/**
 * One `echarts` fence: a picture the document's author drew, not a chart over
 * a connection's rows. It reads nothing from any source, cannot name a
 * relation and — being JSON — cannot carry a function. What it may draw is the
 * document vocabulary in `charts.ts`, and a series outside it is named rather
 * than left as an empty box. See D50, and the deviation recorded next to D35.
 */
import { init } from "echarts/core"
import type { EChartsType } from "echarts/core"
import type { EChartsOption } from "echarts"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"

import { copySource, saveSvg, svgFromDataUrl } from "@/features/content/markdown/blockActions"
import {
  normalizeLayout,
  registerDocumentCharts,
  unsupportedSeries,
} from "@/features/content/markdown/charts"
import BlockChrome from "@/features/content/markdown/BlockChrome.vue"
import { useThemeStore } from "@/stores/theme"
import { t } from "@/shared/i18n"
import { AppCopyButton, AppIconButton, useToast } from "@/shared/ui"

registerDocumentCharts()

const props = defineProps<{ code: string }>()

const theme = useThemeStore()
const toast = useToast()
const host = ref<HTMLElement | null>(null)
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null

const parsed = computed<{ option: EChartsOption } | { failure: string }>(() => {
  let value: unknown
  try {
    value = JSON.parse(props.code)
  } catch {
    return { failure: t("content.markdown.chart.not_json") }
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { failure: t("content.markdown.chart.not_object") }
  }
  const unsupported = unsupportedSeries(value as Record<string, unknown>)
  if (unsupported.length > 0) {
    return {
      failure: t("content.markdown.chart.unsupported", { series: unsupported.join(", ") }),
    }
  }
  return { option: normalizeLayout(value as Record<string, unknown>) as EChartsOption }
})

const failure = ref("")
const drawn = computed(() => !("failure" in parsed.value) && failure.value === "")

function draw() {
  const element = host.value
  const answer = parsed.value
  if (element === null || "failure" in answer) return
  chart?.dispose()
  chart = init(element, theme.dark ? "dark" : undefined, { renderer: "svg" })
  try {
    chart.setOption({ ...answer.option, backgroundColor: "transparent" }, true)
    failure.value = ""
  } catch (cause) {
    // A component this application does not carry: say so instead of leaving
    // half a chart on the page.
    chart.dispose()
    chart = null
    failure.value =
      cause instanceof Error ? cause.message : t("content.markdown.chart.not_drawn")
  }
}

async function copy() {
  await copySource(props.code)
  toast.success(t("content.markdown.chart.copied"))
}

function download() {
  if (chart === null) return
  const svg = svgFromDataUrl(chart.getDataURL({ type: "svg" }))
  if (svg === "") {
    toast.error(t("content.markdown.chart.not_saved"))
    return
  }
  saveSvg(svg, "chart.svg")
}

onMounted(() => {
  draw()
  if (typeof ResizeObserver !== "undefined" && host.value !== null) {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(host.value)
  }
})

watch([() => props.code, () => theme.dark], () => draw())

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <BlockChrome :label="t('content.markdown.chart.label')">
    <template #actions>
      <AppIconButton
        v-if="drawn"
        :icon="appIcons.download"
        :tooltip="t('content.markdown.chart.save')"
        data-testid="echarts-download"
        @click="download"
      />
      <AppCopyButton
        :tooltip="t('content.markdown.chart.copy')"
        data-testid="echarts-copy"
        @click="copy"
      />
    </template>

    <p
      v-if="'failure' in parsed || failure"
      class="echarts-block__failure"
      data-testid="echarts-failure"
    >
      {{ "failure" in parsed ? parsed.failure : failure }}
    </p>
    <div
      v-else
      ref="host"
      class="echarts-block__figure"
      data-testid="echarts-figure"
    />
  </BlockChrome>
</template>

<style scoped>
.echarts-block__figure {
  width: 100%;
  /* Tall enough for a title, a legend and a plot to stand apart. */
  height: 350px;
  padding: var(--dp-space-2);
}
.echarts-block__failure {
  margin: 0;
  padding: var(--dp-space-3);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
</style>
