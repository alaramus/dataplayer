<script setup lang="ts">
import * as pdfjs from "pdfjs-dist"
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist"
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue"

import type { ContentRequest } from "@/client"
import { client } from "@/client/client.gen"
import { formatSize } from "@/features/catalog/nodes"
import { useContent } from "@/features/content/api"
import { pageScale } from "@/features/content/pdfScale"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppSpinner } from "@/shared/ui"

// The renderer runs in a worker, which is where a document is parsed. Named
// through `import.meta.url` so the bundler emits it beside the application
// rather than reaching for a copy on a CDN.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString()

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
}>()

const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({
  node_id: props.nodeId,
  representation: "pdf",
}))
const content = useContent(connectorId, request)

const stage = ref<HTMLElement | null>(null)
const document_ = shallowRef<PDFDocumentProxy | null>(null)
let task: PDFDocumentLoadingTask | null = null
const pageCount = ref(0)
const renderError = ref("")
const rendering = ref(false)
let observer: IntersectionObserver | null = null
let resizes: ResizeObserver | null = null
/** The width the pages on screen were laid out for. */
let laidOutFor = 0

const pdf = computed(() => {
  const value = content.data.value
  return value?.kind === "pdf" ? value : null
})
const details = computed(() => {
  const value = pdf.value
  if (value === null) return ""
  const pages = pageCount.value === 0 ? "" : ` · ${String(pageCount.value)} pages`
  return `PDF ${value.version}${pages} · ${formatSize(value.size_bytes)}`
})
const error = computed(() =>
  content.isError.value
    ? messageOf(content.error.value, "Could not open this document")
    : renderError.value
)

watch(
  () => pdf.value?.stream_url,
  async (url) => {
    if (url === undefined || url === null) return
    await open(client.buildUrl({ url }))
  },
  { immediate: true }
)

async function open(url: string) {
  await close()
  renderError.value = ""
  rendering.value = true
  try {
    // Nothing in the document is allowed to run: no scripting manager is
    // wired and no annotation layer is drawn, so what reaches the screen is
    // pixels, and what is selectable is text nodes this component positions
    // itself (D52). Pages are fetched as they are needed rather than at once.
    task = pdfjs.getDocument({ url, disableAutoFetch: true })
    const loaded = await task.promise
    document_.value = loaded
    pageCount.value = loaded.numPages
    watchWidth()
    await layOutPages(loaded)
  } catch (cause) {
    renderError.value = messageOf(cause, "This document could not be drawn")
  } finally {
    rendering.value = false
  }
}

/**
 * A placeholder per page, and a canvas only for the pages that are looked at:
 * a thousand-page document costs a thousand empty boxes rather than a thousand
 * bitmaps.
 *
 * Laid out again whenever the room changes, because a panel that is not on
 * screen has no width at all — a document opened behind another tab would
 * otherwise be drawn at its own size and scroll sideways when shown.
 */
async function layOutPages(loaded: PDFDocumentProxy) {
  const host = stage.value
  if (host === null || host.clientWidth === 0) return
  laidOutFor = host.clientWidth
  host.replaceChildren()
  observer?.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const element = entry.target as HTMLElement
        observer?.unobserve(element)
        void drawPage(loaded, Number(element.dataset.page), element)
      }
    },
    { root: host, rootMargin: "200px" }
  )

  const first = await loaded.getPage(1)
  const scale = pageScale(host.clientWidth, first.getViewport({ scale: 1 }).width)
  for (let number = 1; number <= loaded.numPages; number += 1) {
    const page = number === 1 ? first : await loaded.getPage(number)
    const viewport = page.getViewport({ scale })
    const slot = window.document.createElement("div")
    slot.className = "pdf-panel__page"
    slot.dataset.page = String(number)
    slot.dataset.testid = `pdf-page-${String(number)}`
    slot.style.width = `${String(Math.floor(viewport.width))}px`
    slot.style.height = `${String(Math.floor(viewport.height))}px`
    slot.style.setProperty("--scale-factor", String(scale))
    host.append(slot)
    if (number === 1) {
      // The first page is drawn at once rather than waited for: intersection
      // is delivered while the browser paints, and a panel that is not being
      // painted — behind another tab, in a window nobody is looking at —
      // would otherwise open on an empty sheet.
      void drawPage(loaded, 1, slot)
      continue
    }
    observer.observe(slot)
  }
}

async function drawPage(loaded: PDFDocumentProxy, number: number, slot: HTMLElement) {
  try {
    const page = await loaded.getPage(number)
    const scale = Number(slot.style.getPropertyValue("--scale-factor"))
    const viewport = page.getViewport({ scale })
    const ratio = window.devicePixelRatio || 1
    const canvas = window.document.createElement("canvas")
    canvas.width = Math.floor(viewport.width * ratio)
    canvas.height = Math.floor(viewport.height * ratio)
    canvas.style.width = `${String(Math.floor(viewport.width))}px`
    canvas.style.height = `${String(Math.floor(viewport.height))}px`
    const context = canvas.getContext("2d")
    if (context === null) return
    context.scale(ratio, ratio)
    await page.render({ canvas, canvasContext: context, viewport }).promise
    slot.append(canvas)

    // The one thing besides pixels that reaches the DOM: text nodes, laid over
    // the page so selection and the browser's own find work.
    const layer = window.document.createElement("div")
    layer.className = "textLayer"
    slot.append(layer)
    const text = new pdfjs.TextLayer({
      textContentSource: await page.getTextContent(),
      container: layer,
      viewport,
    })
    await text.render()
  } catch (cause) {
    renderError.value = messageOf(cause, `Page ${String(number)} could not be drawn`)
  }
}

function watchWidth() {
  const host = stage.value
  if (host === null || resizes !== null) return
  resizes = new ResizeObserver(() => {
    const loaded = document_.value
    if (loaded === null || host.clientWidth === 0) return
    // A few pixels are the scrollbar arriving; a real change is the panel
    // being shown, split or dragged into another column.
    if (Math.abs(host.clientWidth - laidOutFor) < 24) return
    void layOutPages(loaded)
  })
  resizes.observe(host)
}

async function close() {
  observer?.disconnect()
  observer = null
  stage.value?.replaceChildren()
  const loading = task
  task = null
  document_.value = null
  pageCount.value = 0
  // The loading task owns the worker; destroying it stops every request the
  // document still had in flight.
  if (loading !== null) await loading.destroy()
}

async function reload() {
  await content.refetch()
  const url = pdf.value?.stream_url
  if (url) await open(client.buildUrl({ url }))
}

useReloadable(props.panelId, reload)
onBeforeUnmount(() => {
  resizes?.disconnect()
  resizes = null
  void close()
})
</script>

<template>
  <div class="pdf-panel">
    <div class="pdf-panel__head">
      <span data-testid="pdf-details">{{ details }}</span>
      <div class="pdf-panel__commands">
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
        />
      </div>
    </div>

    <AppBanner
      v-if="error"
      tone="error"
      data-testid="content-error"
    >
      {{ error }}
    </AppBanner>
    <AppSpinner v-else-if="content.isPending.value || rendering" />
    <div
      v-show="!error"
      ref="stage"
      class="pdf-panel__stage"
      data-testid="pdf-stage"
    />
  </div>
</template>

<style scoped>
.pdf-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
}
.pdf-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 8px;
  border-bottom: 1px solid var(--dp-border-faint);
  color: var(--dp-text-muted);
  font-size: 11px;
}
.pdf-panel__commands {
  display: flex;
  align-items: center;
  gap: 2px;
}
.pdf-panel__stage {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  min-height: 0;
  overflow: auto;
  padding: 16px;
  background: var(--dp-hover);
}
.pdf-panel__stage :deep(.pdf-panel__page) {
  position: relative;
  flex: none;
  background: #fff;
  box-shadow: 0 1px 4px rgb(0 0 0 / 40%);
}
.pdf-panel__stage :deep(.textLayer) {
  position: absolute;
  inset: 0;
  overflow: hidden;
  line-height: 1;
  text-align: initial;
  opacity: 1;
  forced-color-adjust: none;
  transform-origin: 0 0;
}
.pdf-panel__stage :deep(.textLayer span) {
  position: absolute;
  color: transparent;
  white-space: pre;
  cursor: text;
  transform-origin: 0 0;
}
.pdf-panel__stage :deep(.textLayer ::selection) {
  background: rgb(0 100 255 / 30%);
}
</style>
