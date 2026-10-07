<script setup lang="ts">
import { appIcons } from "@/shared/ui"
/** A bounded Markdown document, rendered, navigated and exported in-browser. */
import "katex/dist/katex.min.css"
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

import type { ContentRequest } from "@/client"
import { client } from "@/client/client.gen"
import { useCatalogLoader, useNodePathLoader } from "@/features/catalog/api"
import { useContent, useContentLoader } from "@/features/content/api"
import { splitDocument } from "@/features/content/markdown/blocks"
import type { DocumentBlock, RichDocumentBlock } from "@/features/content/markdown/blocks"
import ProseBlock from "@/features/content/markdown/ProseBlock.vue"
import RichBlock from "@/features/content/markdown/RichBlock.vue"
import ReadAloudButton from "@/features/speech/ReadAloudButton.vue"
import {
  createHtmlFileName,
  createRenderedHtml,
  printRenderedHtml,
  waitForDocumentRender,
} from "@/features/content/markdown/export"
import { resolveRelativeTarget } from "@/features/content/markdown/relative"
import { outlineProse, renderProse } from "@/features/content/markdown/render"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { errorKindOf, messageOf } from "@/shared/api/errors"
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
const errorKind = computed(() => errorKindOf(content.error.value))
const loadContent = useContentLoader()
const loadPath = useNodePathLoader()
const loadChildren = useCatalogLoader()
const workspace = useWorkspaceActions()
const toast = useToast()

const allowRemoteImages = ref(false)
const outlineOpen = ref(true)
const article = ref<HTMLElement | null>(null)
const searchOpen = ref(false)
const searchQuery = ref("")
const activeSearchIndex = ref(-1)
const searchMatchCount = ref(0)
const activeSection = ref("")
const exporting = ref(false)

const exportItems: MenuItem[] = [
  { name: "html", label: "Rendered HTML", icon: appIcons.html },
  { name: "pdf", label: "Print or save as PDF", icon: appIcons.print },
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

type RenderedBlock = RichDocumentBlock | { type: "prose"; html: string }

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

function toggleSearch(): void {
  searchOpen.value = !searchOpen.value
  if (!searchOpen.value) searchQuery.value = ""
}

function closeSearch(): void {
  searchOpen.value = false
  searchQuery.value = ""
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

/** The nodes of a level, which is all a relative reference walks over. */
async function childrenOf(connectorId: string, nodeId: string | null) {
  return (await loadChildren(connectorId, nodeId)).nodes
}

async function resolveTarget(reference: string) {
  return resolveRelativeTarget(props.connectorId, props.nodeId, reference, loadPath, childrenOf)
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

useReloadable(() => props.panelId, async () => {
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
  <div class="markdown-panel">
    <!-- Above the banner rather than inside the branch that draws a document:
         a document that failed to load is exactly when re-reading it is worth
         offering, and the row that offers it must be on screen to be pressed. -->
    <div class="markdown-panel__head dp-scroll-edges">
      <div class="markdown-panel__tools">
        <template v-if="contentDocument">
          <AppButton
            v-if="headings.length > 0"
            variant="quiet"
            size="sm"
            :icon="appIcons.toc"
            :label="`Contents (${String(headings.length)})`"
            layout="toolbar"
            data-testid="markdown-toggle-contents"
            @click="outlineOpen = !outlineOpen"
          />
          <AppIconButton
            :icon="appIcons.search"
            :tooltip="searchOpen ? 'Close search' : 'Search document'"
            :aria-pressed="searchOpen"
            data-testid="markdown-search-toggle"
            @click="toggleSearch"
          />
          <template v-if="searchOpen">
            <AppInput
              v-model="searchQuery"
              compact
              clearable
              placeholder="Search document"
              class="markdown-panel__search"
              data-testid="markdown-search"
              @keyup.esc="closeSearch"
            />
            <span
              class="markdown-panel__search-position"
              data-testid="markdown-search-position"
            >
              {{ searchPosition }}
            </span>
            <AppIconButton
              :icon="appIcons.keyboardArrowUp"
              tooltip="Previous match"
              :disable="searchMatchCount === 0"
              data-testid="markdown-search-previous"
              @click="stepSearch(-1)"
            />
            <AppIconButton
              :icon="appIcons.keyboardArrowDown"
              tooltip="Next match"
              :disable="searchMatchCount === 0"
              data-testid="markdown-search-next"
              @click="stepSearch(1)"
            />
          </template>
        </template>
      </div>
      <div class="markdown-panel__actions">
        <template v-if="contentDocument">
          <ReadAloudButton
            :text="contentDocument.text"
            strip-markdown
            listen-label="Listen to document"
            testid="markdown-listen"
          />
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.download"
            label="Export"
            layout="toolbar"
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
            :icon="appIcons.code"
            :label="sourceTitle ?? 'View as text'"
            layout="toolbar"
            data-testid="markdown-view-source"
            @click="showSource"
          />
        </template>
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
        />
      </div>
    </div>

    <SourceErrorBanner
      v-if="error"
      :connector-id="connectorId"
      :error-kind="errorKind"
      data-testid="content-error"
    >
      {{ error }}
    </SourceErrorBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <template v-else-if="contentDocument">
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
          <div class="markdown-panel__outline-title dp-overline">
            On this page
          </div>
          <AppButton
            v-for="heading in headings"
            :key="heading.id"
            variant="quiet"
            size="sm"
            :label="heading.title"
            layout="navigation"
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
          class="markdown-panel__document dp-panel-scroll"
          data-testid="markdown-document"
          @click="onDocumentClick"
          @scroll.passive="updateActiveHeading"
        >
          <template
            v-for="(block, index) in blocks"
            :key="`${block.type}-${String(index)}`"
          >
            <ProseBlock
              v-if="block.type === 'prose'"
              class="markdown-panel__prose"
              :html="block.html"
            />
            <RichBlock
              v-else
              :block="block"
              :eager="exporting"
            />
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
  padding: var(--dp-space-1);
  gap: var(--dp-space-1);
}
.markdown-panel__head,
.markdown-panel__tools,
.markdown-panel__actions {
  display: flex;
  align-items: center;
}
/* One scrolling row of commands (D187): a narrow panel reaches past its edge,
   with a shadow where it continues, rather than putting the second half of
   the head on a line of its own. */
.markdown-panel__head {
  flex-wrap: nowrap;
  justify-content: flex-start;
  gap: var(--dp-space-2);
  min-height: var(--dp-toolbar-height);
  padding: var(--dp-space-1) var(--dp-space-2);
  overflow-x: auto;
  border-bottom: 1px solid var(--dp-border-faint);
}
.markdown-panel__tools,
.markdown-panel__actions {
  gap: var(--dp-space-1);
}
/* Nothing in the row squeezes: a tool that gave way would paint over its
   neighbour, so the row keeps its width and the head scrolls instead. */
.markdown-panel__tools {
  flex: none;
}
.markdown-panel__tools > *,
.markdown-panel__actions > * {
  flex: none;
}
.markdown-panel__search {
  width: min(220px, 30vw);
  min-width: 120px;
  margin-left: var(--dp-space-1);
}
.markdown-panel__actions {
  flex: none;
  margin-left: auto;
}
.markdown-panel__search-position {
  min-width: 36px;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
  text-align: center;
}
.markdown-panel__remote {
  display: flex;
  align-items: center;
  gap: var(--dp-space-3);
  padding: var(--dp-space-1) var(--dp-space-2);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
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
  padding: var(--dp-space-3) var(--dp-space-2);
  border-right: 1px solid var(--dp-border-faint);
}
.markdown-panel__outline-title {
  padding: 0 var(--dp-space-2) var(--dp-space-1);
}
.markdown-panel__outline-entry {
  display: flex;
  width: 100%;
  justify-content: flex-start;
  color: var(--dp-text-muted);
  text-align: left;
}
.markdown-panel__outline-entry--2 {
  padding-left: var(--dp-space-3);
}
.markdown-panel__outline-entry--3 {
  padding-left: calc(2 * var(--dp-space-3));
  font-size: var(--dp-font-size-xs);
}
/* The section on screen, drawn as a current tab is (D186): in blue it read
   as a link among links. */
.markdown-panel__outline-entry--active {
  background: var(--dp-tab-current);
  color: var(--dp-text);
  font-weight: 500;
}
.markdown-panel__document {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-4) var(--dp-space-5);
  color: var(--dp-text);
  font-size: var(--dp-prose-font-size);
  line-height: 1.65;
}
.markdown-panel__document :deep(mark[data-search-highlight]) {
  border-radius: var(--dp-radius-control);
  background: color-mix(in srgb, var(--dp-find) 45%, transparent);
  color: inherit;
}
.markdown-panel__document :deep(mark.markdown-search-active) {
  outline: 2px solid var(--dp-find);
  background: color-mix(in srgb, var(--dp-find) 70%, transparent);
}
@media (max-width: 760px) {
  .markdown-panel__outline {
    flex-basis: 170px;
  }
}
</style>
