<script setup lang="ts">
/**
 * Rendered Markdown prose, typeset once for a document and for the agent's
 * answer. What the prose says stays with the caller — a document numbers its
 * headings and a chat does not (RichBlock) — but not how it looks: the chat
 * had no rules of its own, and Quasar's typography drew a `###` at 48 pixels.
 *
 * The body size is the container's (`--dp-prose-font-size`), so what stands
 * beside the prose reads at the same size; the headings' sizes are set here.
 */
defineProps<{ html: string }>()
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- every string given here comes from
  markdown/render.ts, which sanitises it (sanitize.ts). -->
  <div
    class="prose-block"
    v-html="html"
  />
</template>

<style scoped>
/* Every level is set, because a level left out falls to Quasar's h1 to h6:
   a display face from 96 pixels down, light and letter-spaced. */
.prose-block :deep(:is(h1, h2, h3, h4, h5, h6)) {
  margin: var(--dp-space-5) 0 var(--dp-space-2);
  font-size: 1em;
  font-weight: 600;
  line-height: var(--dp-prose-heading-line-height);
  letter-spacing: normal;
  scroll-margin-top: 12px;
}
.prose-block :deep(h1) {
  font-size: var(--dp-prose-heading-1);
}
.prose-block :deep(h2) {
  font-size: var(--dp-prose-heading-2);
}
.prose-block :deep(h3) {
  font-size: var(--dp-prose-heading-3);
}
.prose-block :deep(p),
.prose-block :deep(ul),
.prose-block :deep(ol),
.prose-block :deep(blockquote) {
  margin: var(--dp-space-2) 0;
}
.prose-block :deep(ul),
.prose-block :deep(ol) {
  padding-inline-start: var(--dp-space-5);
}
/* A task's tick box is its marker: with the list's bullet as well, every
   task started with two. */
.prose-block :deep(.task-list-item) {
  list-style: none;
}
.prose-block :deep(.task-list-item-checkbox) {
  margin: 0 var(--dp-space-1) 0 calc(-1 * var(--dp-space-5) + var(--dp-space-1));
}
.prose-block :deep(blockquote) {
  padding: var(--dp-space-half) var(--dp-space-3);
  border-inline-start: 3px solid var(--dp-border-faint);
  color: var(--dp-text-muted);
}
.prose-block :deep(code) {
  padding: 1px var(--dp-space-1);
  border-radius: var(--dp-radius-control);
  background: var(--dp-hover);
  font-family: var(--dp-font-mono);
  font-size: var(--dp-prose-code-font-size);
}
/* A table wider than the column scrolls inside itself rather than pushing
   the column wider. */
.prose-block :deep(table) {
  display: block;
  max-width: 100%;
  overflow: auto;
  border-collapse: collapse;
  margin: var(--dp-space-3) 0;
}
.prose-block :deep(th),
.prose-block :deep(td) {
  padding: var(--dp-space-1) var(--dp-space-2);
  border: 1px solid var(--dp-border-faint);
  text-align: start;
}
.prose-block :deep(th) {
  background: var(--dp-chrome-raised);
}
.prose-block :deep(img) {
  max-width: 100%;
}
.prose-block :deep(img[data-remote-blocked]),
.prose-block :deep(img[data-relative-source]),
.prose-block :deep(img[data-relative-error]) {
  display: inline-block;
  min-width: 120px;
  min-height: 24px;
  border: 1px dashed var(--dp-border-faint);
  border-radius: var(--dp-radius-control);
}
.prose-block :deep(img[data-relative-error]) {
  border-color: var(--dp-content-error);
}
.prose-block :deep(a) {
  color: var(--dp-link);
}
.prose-block :deep(a[data-relative-link]) {
  border-bottom: 1px dotted currentColor;
  cursor: pointer;
}
.prose-block :deep(a[data-relative-loading]) {
  cursor: wait;
  opacity: var(--dp-opacity-dim);
}
.prose-block :deep(.katex) {
  display: inline-block;
  line-height: normal;
  vertical-align: middle;
}
.prose-block :deep(.katex-display) {
  overflow-x: auto;
  overflow-y: hidden;
  margin: var(--dp-space-3) 0;
  padding: var(--dp-space-half) 0;
}
.prose-block :deep(hr) {
  border: 0;
  border-top: 1px solid var(--dp-border-faint);
}
</style>
