<script setup lang="ts">
/** A bounded Markdown document, rendered, navigated and exported in-browser. */
import "katex/dist/katex.min.css"
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from "vue"

import type { ContentRequest } from "@/client"
import { client } from "@/client/client.gen"
import { useCatalogLoader, useNodePathLoader } from "@/features/catalog/api"
import { useContent, useContentLoader } from "@/features/content/api"
import AgentBlock from "@/features/content/markdown/AgentBlock.vue"
import DeferredBlock from "@/features/content/markdown/DeferredBlock.vue"
import { splitDocument } from "@/features/content/markdown/blocks"
import type { DocumentBlock } from "@/features/content/markdown/blocks"
import {
  createHtmlFileName,
  createRenderedHtml,
  printRenderedHtml,
  waitForDocumentRender,
} from "@/features/content/markdown/export"
import { resolveRelativeTarget } from "@/features/content/markdown/relative"
import { outlineProse, renderProse } from "@/features/content/markdown/render"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { saveBrowserDownload } from "@/shared/download"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppIconButton,
  AppInput,
  AppMenu,
  AppSpinner,
  useToast,
} from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

const CodeFence = defineAsyncComponent(() => import("@/features/content/markdown/CodeFence.vue"))
const EchartsBlock = defineAsyncComponent(
  () => import("@/features/content/markdown/EchartsBlock.vue")
)
const MermaidBlock = defineAsyncComponent(
  () => import("@/features/content/markdown/MermaidBlock.vue")
)
const SvgBlock = defineAsyncComponent(() => import("@/features/content/markdown/SvgBlock.vue"))

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  sourceTitle?: string
}>()

const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({
  node_id: props.nodeId,
  representation: "markdown",
}))
const content = useContent(connectorId, request)
const loadContent = useContentLoader()
const loadPath = useNodePathLoader()
const loadChildren = useCatalogLoader()
const workspace = useWorkspaceActions()
const toast = useToast()

const allowRemoteImages = ref(false)
const outlineOpen = ref(true)
const article = ref<HTMLElement | null>(null)
const searchQuery = ref("")
const activeSearchIndex = ref(-1)
const searchMatchCount = ref(0)
const activeSection = ref("")
const exporting = ref(false)

const exportItems: MenuItem[] = [
  { name: "html", label: "Rendered HTML", icon: "html" },
  { name: "pdf", label: "Print or save as PDF", icon: "print" },
]

function showSource() {
  workspace.openRepresentation({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    representations: [{ kind: "text", title: props.sourceTitle ?? "View as text" }],
    describable: false,
  })
}

const contentDocument = computed(() => {
  const value = content.data.value
  return value?.kind === "markdown" ? value : null
})
const sourceBlocks = computed(() => {
  const source = contentDocument.value?.text
  return source === undefined ? [] : splitDocument(source)
})
const outline = computed(() =>
  outlineProse(
    sourceBlocks.value
      .filter((block): block is Extract<DocumentBlock, { type: "prose" }> => block.type === "prose")
      .map((block) => block.content)
  )
)
const headings = computed(() => outline.value.headings)

type RenderedBlock = Exclude<DocumentBlock, { type: "prose" }> | { type: "prose"; html: string }

const blocks = computed<RenderedBlock[]>(() => {
  let proseIndex = 0
  return sourceBlocks.value.map((block) => {
    if (block.type !== "prose") return block
    const headingIds = outline.value.blockHeadingIds[proseIndex] ?? []
    proseIndex += 1
    return {
      type: "prose" as const,
      html: renderProse(block.content, {
        allowRemoteImages: allowRemoteImages.value,
        headingIds,
      }),
    }
  })
})

const blockedImages = computed(() =>
  blocks.value.reduce(
    (total, block) =>
      block.type === "prose" ? total + block.html.split("data-remote-blocked").length - 1 : total,
    0
  )
)
const error = computed(() =>
  content.isError.value ? messageOf(content.error.value, "Could not open this document") : ""
)
const searchPosition = computed(() =>
  searchMatchCount.value === 0
    ? "0/0"
    : `${String(activeSearchIndex.value + 1)}/${String(searchMatchCount.value)}`
)

function elementAt(anchor: string): HTMLElement | null {
  return (
    Array.from(article.value?.querySelectorAll<HTMLElement>("[id]") ?? []).find(
      (element) => element.id === anchor
    ) ?? null
  )
}

function scrollToAnchor(anchor: string, block: ScrollLogicalPosition = "start"): boolean {
  const target = elementAt(anchor)
  if (target === null) return false
  target.scrollIntoView({ behavior: "smooth", block })
  target.focus({ preventScroll: true })
  activeSection.value = anchor
  return true
}

function clearSearchDecorations(): void {
  const root = article.value
  if (root === null) return
  root.querySelectorAll("mark[data-search-highlight]").forEach((mark) => {
    mark.replaceWith(window.document.createTextNode(mark.textContent ?? ""))
  })
  root
    .querySelectorAll<HTMLElement>(
      ".markdown-panel__prose, .agent-block__fields, .agent-block__body"
    )
    .forEach((container) => container.normalize())
}

function showActiveSearchMatch(): void {
  const root = article.value
  if (root === null) return
  const marks = Array.from(root.querySelectorAll<HTMLElement>("mark[data-search-highlight]"))
  marks.forEach((mark) => mark.classList.remove("markdown-search-active"))
  const active = marks[activeSearchIndex.value]
  if (active === undefined) return
  active.classList.add("markdown-search-active")
  active.scrollIntoView({ behavior: "smooth", block: "center" })
}

function applySearchDecorations(): void {
  const root = article.value
  if (root === null) return
  clearSearchDecorations()
  const query = searchQuery.value.trim()
  if (query === "") {
    activeSearchIndex.value = -1
    searchMatchCount.value = 0
    return
  }
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const matcher = new RegExp(escaped, "giu")
  const textNodes: Text[] = []
  root
    .querySelectorAll<HTMLElement>(
      ".markdown-panel__prose, .agent-block__fields, .agent-block__body"
    )
    .forEach((container) => {
      const walker = window.document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement
          if (
            !node.textContent?.trim() ||
            parent === null ||
            parent.closest('mark, script, style, [aria-hidden="true"]') !== null
          ) {
            return NodeFilter.FILTER_REJECT
          }
          return NodeFilter.FILTER_ACCEPT
        },
      })
      let node = walker.nextNode()
      while (node !== null) {
        textNodes.push(node as Text)
        node = walker.nextNode()
      }
    })

  let matchIndex = 0
  textNodes.forEach((textNode) => {
    const matches = [...textNode.data.matchAll(matcher)]
    if (matches.length === 0) return
    const fragment = window.document.createDocumentFragment()
    let cursor = 0
    matches.forEach((match) => {
      const index = match.index ?? 0
      if (index > cursor) {
        fragment.append(window.document.createTextNode(textNode.data.slice(cursor, index)))
      }
      const mark = window.document.createElement("mark")
      mark.dataset.searchHighlight = ""
      mark.id = `markdown-search-${String(matchIndex)}`
      mark.textContent = match[0]
      fragment.append(mark)
      matchIndex += 1
      cursor = index + match[0].length
    })
    if (cursor < textNode.data.length) {
      fragment.append(window.document.createTextNode(textNode.data.slice(cursor)))
    }
    textNode.replaceWith(fragment)
  })
  searchMatchCount.value = matchIndex
  activeSearchIndex.value = matchIndex === 0 ? -1 : 0
  showActiveSearchMatch()
}

function stepSearch(direction: number): void {
  const total = searchMatchCount.value
  if (total === 0) return
  activeSearchIndex.value = (activeSearchIndex.value + direction + total) % total
  showActiveSearchMatch()
}

function updateActiveHeading(): void {
  const root = article.value
  if (root === null || headings.value.length === 0) {
    activeSection.value = ""
    return
  }
  if (root.scrollTop + root.clientHeight >= root.scrollHeight - 8) {
    activeSection.value = headings.value.at(-1)?.id ?? ""
    return
  }
  const activationLine = root.getBoundingClientRect().top + 16
  let current = headings.value[0]?.id ?? ""
  for (const heading of headings.value) {
    const element = elementAt(heading.id)
    if (element !== null && element.getBoundingClientRect().top <= activationLine) {
      current = heading.id
    } else {
      break
    }
  }
  activeSection.value = current
}

async function resolveTarget(reference: string) {
  return resolveRelativeTarget(props.connectorId, props.nodeId, reference, loadPath, loadChildren)
}

let resourceEpoch = 0
let imageObserver: IntersectionObserver | null = null
const imageTasks = new Map<HTMLImageElement, Promise<void>>()

function stopImageObserver(): void {
  imageObserver?.disconnect()
  imageObserver = null
}

function resolveRelativeImage(image: HTMLImageElement, epoch: number): Promise<void> {
  const existing = imageTasks.get(image)
  if (existing !== undefined) return existing
  const reference = image.dataset.relativeSource ?? image.dataset.relativeReference
  if (reference === undefined) return Promise.resolve()
  image.dataset.relativeLoading = ""
  const task = (async () => {
    try {
      const target = await resolveTarget(reference)
      if (!target.node.representations.some((item) => item.kind === "image")) {
        throw new Error(`${target.node.name} does not declare an image viewer`)
      }
      const result = await loadContent(props.connectorId, {
        node_id: target.node.id,
        representation: "image",
      })
      if (result.kind !== "image" || !result.preview_url) {
        throw new Error("The source did not return a verified image preview")
      }
      if (epoch !== resourceEpoch || article.value?.contains(image) !== true) return
      image.onload = () => {
        delete image.dataset.relativeError
        image.removeAttribute("title")
      }
      image.onerror = () => {
        if (article.value?.contains(image) !== true) return
        image.removeAttribute("src")
        image.dataset.relativeError = ""
        image.title = "The verified preview could not be loaded"
      }
      image.src = client.buildUrl({ url: result.preview_url })
      image.dataset.relativeReference = reference
      delete image.dataset.relativeSource
      delete image.dataset.relativeLoading
    } catch (cause) {
      if (epoch !== resourceEpoch || article.value?.contains(image) !== true) return
      const failure = cause instanceof Error ? cause.message : "This image could not be resolved"
      delete image.dataset.relativeSource
      delete image.dataset.relativeLoading
      image.dataset.relativeError = ""
      image.title = failure
      if (!image.alt) image.alt = failure
    }
  })().finally(() => imageTasks.delete(image))
  imageTasks.set(image, task)
  return task
}

async function scanRelativeImages(eager: boolean): Promise<void> {
  const root = article.value
  if (root === null) return
  const epoch = resourceEpoch
  const selector = eager
    ? "img[data-relative-source], img[data-relative-reference]"
    : "img[data-relative-source]"
  const images = Array.from(root.querySelectorAll<HTMLImageElement>(selector))
  if (eager || typeof IntersectionObserver === "undefined") {
    stopImageObserver()
    await Promise.all([
      ...imageTasks.values(),
      ...images.map((image) => resolveRelativeImage(image, epoch)),
    ])
    return
  }
  stopImageObserver()
  imageObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return
        imageObserver?.unobserve(entry.target)
        void resolveRelativeImage(entry.target as HTMLImageElement, epoch)
      })
    },
    { root, rootMargin: "240px 0px" }
  )
  images.forEach((image) => imageObserver?.observe(image))
}

async function onDocumentClick(event: MouseEvent): Promise<void> {
  const origin = event.target
  if (!(origin instanceof Element)) return
  const link = origin.closest<HTMLAnchorElement>("a")
  if (link === null || article.value?.contains(link) !== true) return
  const href = link.getAttribute("href")
  if (href?.startsWith("#")) {
    event.preventDefault()
    let fragment = ""
    try {
      fragment = decodeURIComponent(href.slice(1))
    } catch {
      toast.error("This document fragment has invalid percent encoding")
      return
    }
    if (!scrollToAnchor(fragment)) toast.info(`No section named ${fragment} is in this document`)
    return
  }
  const reference = link.dataset.relativeLink
  if (reference === undefined) return
  event.preventDefault()
  if (link.dataset.relativeLoading !== undefined) return
  link.dataset.relativeLoading = ""
  try {
    const target = await resolveTarget(reference)
    if (target.node.id === props.nodeId && target.fragment) {
      if (!scrollToAnchor(target.fragment)) {
        toast.info(`No section named ${target.fragment} is in this document`)
      }
      return
    }
    if (target.node.representations.length === 0) {
      workspace.revealInCatalog(props.connectorId, target.node.id, target.node.name)
      return
    }
    workspace.openRepresentation({
      connectorId: props.connectorId,
      nodeId: target.node.id,
      title: target.node.name,
      connectorName: props.connectorName,
      adapterType: props.adapterType,
      representations: target.node.representations,
      describable: target.node.describable === true,
      ...(target.fragment === "" ? {} : { fragment: target.fragment }),
    })
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : "This relative link could not be opened")
  } finally {
    delete link.dataset.relativeLoading
  }
}

async function consumeDocumentTarget(): Promise<void> {
  if (contentDocument.value === null) return
  const target = workspace.takeDocumentTarget?.(props.connectorId, props.nodeId)
  if (target === null || target === undefined) return
  await nextTick()
  if (!scrollToAnchor(target.fragment)) {
    toast.info(`No section named ${target.fragment} is in this document`)
  }
}

async function exportDocument(kind: "html" | "pdf"): Promise<void> {
  const root = article.value
  if (root === null || exporting.value) return
  exporting.value = true
  try {
    await nextTick()
    await scanRelativeImages(true)
    await waitForDocumentRender(root)
    const html = await createRenderedHtml(root, props.title)
    if (kind === "html") {
      saveBrowserDownload(
        new Blob([html], { type: "text/html;charset=utf-8" }),
        createHtmlFileName(props.title)
      )
      toast.success("Rendered HTML exported")
    } else {
      printRenderedHtml(html)
    }
  } catch {
    toast.error("This rendered document could not be exported")
  } finally {
    exporting.value = false
  }
}

function chooseExport(name: string): void {
  if (name === "html" || name === "pdf") void exportDocument(name)
}

useReloadable(props.panelId, async () => {
  await content.refetch()
})

watch(
  blocks,
  async () => {
    resourceEpoch += 1
    stopImageObserver()
    await nextTick()
    await scanRelativeImages(false)
    updateActiveHeading()
  },
  { flush: "post", immediate: true }
)
watch(
  [blocks, searchQuery],
  async () => {
    await nextTick()
    applySearchDecorations()
  },
  { flush: "post" }
)
watch(
  () => workspace.documentTarget?.value ?? null,
  () => void consumeDocumentTarget(),
  { immediate: true }
)
watch(contentDocument, () => void consumeDocumentTarget())

onBeforeUnmount(() => {
  resourceEpoch += 1
  stopImageObserver()
})
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- every prose string below comes from
  markdown/sanitize.ts; diagrams have their own SVG sanitising boundary. -->
  <div class="markdown-panel">
    <AppBanner
      v-if="error"
      tone="error"
      data-testid="content-error"
    >
      {{ error }}
    </AppBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <template v-else-if="contentDocument">
      <div class="markdown-panel__head">
        <div class="markdown-panel__tools">
          <AppButton
            v-if="headings.length > 0"
            variant="quiet"
            size="sm"
            icon="toc"
            :label="`Contents (${String(headings.length)})`"
            data-testid="markdown-toggle-contents"
            @click="outlineOpen = !outlineOpen"
          />
          <AppInput
            v-model="searchQuery"
            compact
            clearable
            placeholder="Search document"
            class="markdown-panel__search"
            data-testid="markdown-search"
          >
            <template #prepend>
              <q-icon name="search" />
            </template>
          </AppInput>
          <span
            class="markdown-panel__search-position"
            data-testid="markdown-search-position"
          >
            {{ searchPosition }}
          </span>
          <AppIconButton
            icon="keyboard_arrow_up"
            tooltip="Previous match"
            :disable="searchMatchCount === 0"
            data-testid="markdown-search-previous"
            @click="stepSearch(-1)"
          />
          <AppIconButton
            icon="keyboard_arrow_down"
            tooltip="Next match"
            :disable="searchMatchCount === 0"
            data-testid="markdown-search-next"
            @click="stepSearch(1)"
          />
        </div>
        <div class="markdown-panel__actions">
          <AppButton
            variant="quiet"
            size="sm"
            icon="download"
            label="Export"
            :loading="exporting"
            data-testid="markdown-export"
          >
            <AppMenu
              :items="exportItems"
              @select="chooseExport"
            />
          </AppButton>
          <AppButton
            variant="quiet"
            size="sm"
            icon="code"
            :label="sourceTitle ?? 'View as text'"
            data-testid="markdown-view-source"
            @click="showSource"
          />
        </div>
      </div>
      <AppBanner
        v-if="contentDocument.truncated"
        tone="warning"
        data-testid="markdown-truncated"
      >
        This document is larger than the rendering limit, so only its beginning is shown. Its whole
        source opens in the editor.
      </AppBanner>
      <AppBanner
        v-if="contentDocument.notice"
        tone="warning"
        data-testid="markdown-notice"
      >
        {{ contentDocument.notice }}
      </AppBanner>
      <div
        v-if="blockedImages > 0 || allowRemoteImages"
        class="markdown-panel__remote"
      >
        <AppCheckbox
          v-model="allowRemoteImages"
          dense
          label="Load images from other sites"
          data-testid="markdown-allow-remote"
        />
        <span
          v-if="!allowRemoteImages"
          class="markdown-panel__remote-note"
        >
          {{ blockedImages }} image(s) in this document are hosted elsewhere and were not requested.
        </span>
      </div>

      <div class="markdown-panel__body">
        <aside
          v-if="outlineOpen && headings.length > 0"
          class="markdown-panel__outline"
          aria-label="Table of contents"
          data-testid="markdown-contents"
        >
          <div class="markdown-panel__outline-title">
            On this page
          </div>
          <AppButton
            v-for="heading in headings"
            :key="heading.id"
            variant="quiet"
            size="sm"
            :label="heading.title"
            :class="[
              'markdown-panel__outline-entry',
              `markdown-panel__outline-entry--${String(Math.min(heading.level, 3))}`,
              { 'markdown-panel__outline-entry--active': activeSection === heading.id },
            ]"
            :aria-current="activeSection === heading.id ? 'location' : undefined"
            :data-testid="`markdown-heading-${heading.id}`"
            @click="scrollToAnchor(heading.id)"
          />
        </aside>

        <article
          ref="article"
          class="markdown-panel__document"
          data-testid="markdown-document"
          @click="onDocumentClick"
          @scroll.passive="updateActiveHeading"
        >
          <template
            v-for="(block, index) in blocks"
            :key="`${block.type}-${String(index)}`"
          >
            <div
              v-if="block.type === 'prose'"
              class="markdown-panel__prose"
              v-html="block.html"
            />
            <DeferredBlock
              v-else-if="block.type === 'mermaid'"
              :eager="exporting"
            >
              <MermaidBlock :code="block.code" />
            </DeferredBlock>
            <DeferredBlock
              v-else-if="block.type === 'echarts'"
              :eager="exporting"
            >
              <EchartsBlock :code="block.code" />
            </DeferredBlock>
            <DeferredBlock
              v-else-if="block.type === 'svg'"
              :eager="exporting"
            >
              <SvgBlock :code="block.code" />
            </DeferredBlock>
            <DeferredBlock
              v-else-if="block.type === 'code'"
              :eager="exporting"
            >
              <CodeFence
                :language="block.language"
                :code="block.code"
              />
            </DeferredBlock>
            <AgentBlock
              v-else-if="block.type === 'agent'"
              :kind="block.kind"
              :code="block.code"
            />
            <p
              v-else
              class="markdown-panel__oversized"
              data-testid="markdown-oversized"
            >
              This {{ block.language }} block is too large to draw.
            </p>
          </template>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped>
.markdown-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
  gap: 4px;
}
.markdown-panel__head,
.markdown-panel__tools,
.markdown-panel__actions {
  display: flex;
  align-items: center;
}
.markdown-panel__head {
  justify-content: space-between;
  gap: 8px;
  min-height: 40px;
  padding: 2px 8px;
  border-bottom: 1px solid var(--dp-border-faint);
}
.markdown-panel__tools,
.markdown-panel__actions {
  gap: 2px;
}
.markdown-panel__tools {
  min-width: 0;
}
.markdown-panel__search {
  width: min(220px, 30vw);
  margin-left: 4px;
}
.markdown-panel__search-position {
  min-width: 36px;
  color: var(--dp-text-muted);
  font-size: 11px;
  text-align: center;
}
.markdown-panel__remote {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 8px;
  color: var(--dp-text-muted);
  font-size: 11px;
}
.markdown-panel__remote-note {
  min-width: 0;
}
.markdown-panel__body {
  display: flex;
  flex: 1;
  min-height: 0;
}
.markdown-panel__outline {
  flex: 0 0 210px;
  overflow: auto;
  padding: 12px 8px;
  border-right: 1px solid var(--dp-border-faint);
}
.markdown-panel__outline-title {
  padding: 0 8px 6px;
  color: var(--dp-text-muted);
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.markdown-panel__outline-entry {
  display: flex;
  width: 100%;
  justify-content: flex-start;
  color: var(--dp-text-muted);
  text-align: left;
}
.markdown-panel__outline-entry :deep(.q-btn__content) {
  width: 100%;
  justify-content: flex-start;
  text-align: left;
}
.markdown-panel__outline-entry--2 {
  padding-left: 12px;
}
.markdown-panel__outline-entry--3 {
  padding-left: 24px;
  font-size: 11px;
}
.markdown-panel__outline-entry--active {
  color: var(--dp-link);
  font-weight: 600;
}
.markdown-panel__document {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 16px 20px;
  color: var(--dp-text-strong);
  font-size: 13px;
  line-height: 1.6;
}
.markdown-panel__oversized {
  margin: 12px 0;
  color: var(--dp-text-muted);
  font-size: 12px;
}
.markdown-panel__prose :deep(h1),
.markdown-panel__prose :deep(h2),
.markdown-panel__prose :deep(h3) {
  margin: 20px 0 8px;
  font-weight: 600;
  line-height: 1.3;
  scroll-margin-top: 12px;
}
.markdown-panel__prose :deep(h1) {
  font-size: 20px;
}
.markdown-panel__prose :deep(h2) {
  font-size: 16px;
}
.markdown-panel__prose :deep(h3) {
  font-size: 14px;
}
.markdown-panel__prose :deep(p),
.markdown-panel__prose :deep(ul),
.markdown-panel__prose :deep(ol),
.markdown-panel__prose :deep(blockquote) {
  margin: 8px 0;
}
.markdown-panel__prose :deep(ul),
.markdown-panel__prose :deep(ol) {
  padding-left: 22px;
}
.markdown-panel__prose :deep(blockquote) {
  padding: 2px 12px;
  border-left: 3px solid var(--dp-border-faint);
  color: var(--dp-text-muted);
}
.markdown-panel__prose :deep(code) {
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--dp-hover);
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}
.markdown-panel__prose :deep(table) {
  border-collapse: collapse;
  margin: 12px 0;
}
.markdown-panel__prose :deep(th),
.markdown-panel__prose :deep(td) {
  padding: 4px 10px;
  border: 1px solid var(--dp-border-faint);
  text-align: left;
}
.markdown-panel__prose :deep(th) {
  background: var(--dp-chrome-raised);
}
.markdown-panel__prose :deep(img) {
  max-width: 100%;
}
.markdown-panel__prose :deep(img[data-remote-blocked]),
.markdown-panel__prose :deep(img[data-relative-source]),
.markdown-panel__prose :deep(img[data-relative-error]) {
  display: inline-block;
  min-width: 120px;
  min-height: 24px;
  border: 1px dashed var(--dp-border-faint);
  border-radius: 3px;
}
.markdown-panel__prose :deep(img[data-relative-error]) {
  border-color: var(--dp-content-error);
}
.markdown-panel__prose :deep(a) {
  color: var(--dp-link);
}
.markdown-panel__prose :deep(a[data-relative-link]) {
  border-bottom: 1px dotted currentColor;
  cursor: pointer;
}
.markdown-panel__prose :deep(a[data-relative-loading]) {
  cursor: wait;
  opacity: 0.7;
}
.markdown-panel__document :deep(mark[data-search-highlight]) {
  border-radius: 2px;
  background: color-mix(in srgb, var(--dp-find) 45%, transparent);
  color: inherit;
}
.markdown-panel__document :deep(mark.markdown-search-active) {
  outline: 2px solid var(--dp-find);
  background: color-mix(in srgb, var(--dp-find) 70%, transparent);
}
.markdown-panel__prose :deep(.katex) {
  display: inline-block;
  line-height: normal;
  vertical-align: middle;
}
.markdown-panel__prose :deep(.katex-display) {
  overflow-x: auto;
  overflow-y: hidden;
  margin: 14px 0;
  padding: 2px 0;
}
.markdown-panel__prose :deep(hr) {
  border: 0;
  border-top: 1px solid var(--dp-border-faint);
}

@media (max-width: 760px) {
  .markdown-panel__head {
    align-items: flex-start;
    flex-direction: column;
  }
  .markdown-panel__actions {
    align-self: flex-end;
  }
  .markdown-panel__outline {
    flex-basis: 170px;
  }
}
</style>
