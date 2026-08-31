<script setup lang="ts">
/**
 * A Markdown document, rendered. The server sends its source and nothing else;
 * every step from those characters to DOM happens here. See D50.
 */
import "katex/dist/katex.min.css"
import { computed, defineAsyncComponent, ref } from "vue"

import type { ContentRequest } from "@/client"
import { useContent } from "@/features/content/api"
import DeferredBlock from "@/features/content/markdown/DeferredBlock.vue"
import { splitDocument } from "@/features/content/markdown/blocks"
import type { DocumentBlock } from "@/features/content/markdown/blocks"
import { renderProse } from "@/features/content/markdown/render"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppCheckbox, AppSpinner } from "@/shared/ui"

// A callout is text in a coloured frame: cheap, and part of reading the
// document rather than something to wait for.
const AgentBlock = defineAsyncComponent(
  () => import("@/features/content/markdown/AgentBlock.vue")
)
// Heavy by construction, and most documents ask for none of them.
const CodeFence = defineAsyncComponent(
  () => import("@/features/content/markdown/CodeFence.vue")
)
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
const workspace = useWorkspaceActions()
const allowRemoteImages = ref(false)

/** The document's other representation: the same bytes, in the editor. */
function showSource() {
  workspace.openRepresentation({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    representations: [{ kind: "text", title: props.sourceTitle ?? "View as text" }],
    // A file has no structure of its own to describe.
    describable: false,
  })
}

const document = computed(() => {
  const value = content.data.value
  return value?.kind === "markdown" ? value : null
})

type RenderedBlock = Exclude<DocumentBlock, { type: "prose" }> | { type: "prose"; html: string }

const blocks = computed<RenderedBlock[]>(() => {
  const source = document.value?.text
  if (source === undefined) return []
  return splitDocument(source).map((block) =>
    block.type === "prose"
      ? {
          type: "prose" as const,
          html: renderProse(block.content, { allowRemoteImages: allowRemoteImages.value }),
        }
      : block
  )
})

const blockedImages = computed(() =>
  blocks.value.reduce(
    (total, block) =>
      block.type === "prose"
        ? total + block.html.split("data-remote-blocked").length - 1
        : total,
    0
  )
)

const error = computed(() =>
  content.isError.value
    ? messageOf(content.error.value, "Could not open this document")
    : ""
)

useReloadable(props.panelId, async () => {
  await content.refetch()
})
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- every string below comes from
  features/content/markdown/sanitize.ts, which exists for exactly this and is
  covered by sanitize.spec.ts. Rendering a document without v-html would mean
  building the DOM by hand from the same HTML. -->
  <div class="markdown-panel">
    <AppBanner
      v-if="error"
      tone="error"
      data-testid="content-error"
    >
      {{ error }}
    </AppBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <template v-else-if="document">
      <div class="markdown-panel__head">
        <AppButton
          variant="quiet"
          size="sm"
          icon="code"
          :label="sourceTitle ?? 'View as text'"
          data-testid="markdown-view-source"
          @click="showSource"
        />
      </div>
      <AppBanner
        v-if="document.truncated"
        tone="warning"
        data-testid="markdown-truncated"
      >
        This document is larger than the rendering limit, so only its beginning is
        shown. Its whole source opens in the editor.
      </AppBanner>
      <AppBanner
        v-if="document.notice"
        tone="warning"
        data-testid="markdown-notice"
      >
        {{ document.notice }}
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
          {{ blockedImages }} image(s) in this document are hosted elsewhere and were
          not requested.
        </span>
      </div>

      <article
        class="markdown-panel__document"
        data-testid="markdown-document"
      >
        <template
          v-for="(block, index) in blocks"
          :key="`${block.type}-${index}`"
        >
          <div
            v-if="block.type === 'prose'"
            class="markdown-panel__prose"
            v-html="block.html"
          />
          <DeferredBlock v-else-if="block.type === 'mermaid'">
            <MermaidBlock :code="block.code" />
          </DeferredBlock>
          <DeferredBlock v-else-if="block.type === 'echarts'">
            <EchartsBlock :code="block.code" />
          </DeferredBlock>
          <DeferredBlock v-else-if="block.type === 'svg'">
            <SvgBlock :code="block.code" />
          </DeferredBlock>
          <DeferredBlock v-else-if="block.type === 'code'">
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
.markdown-panel__head {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 32px;
  padding: 0 8px;
  border-bottom: 1px solid var(--dp-border-faint);
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
.markdown-panel__document {
  flex: 1;
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
.markdown-panel__prose :deep(img[data-remote-blocked]) {
  display: inline-block;
  min-width: 120px;
  min-height: 24px;
  border: 1px dashed var(--dp-border-faint);
  border-radius: 3px;
}
.markdown-panel__prose :deep(a) {
  color: var(--dp-link);
}
/* Inert, so it must not invite a click that does nothing. */
.markdown-panel__prose :deep(a[data-unresolved-link]) {
  border-bottom: 1px dotted var(--dp-border);
  color: var(--dp-text-muted);
  cursor: default;
}
/*
 * Tall inline maths — a sum with limits, a fraction — overflows a line box laid
 * out for text and collides with the line above it. An inline block is measured
 * by its own height, so the paragraph makes room instead.
 */
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
</style>
