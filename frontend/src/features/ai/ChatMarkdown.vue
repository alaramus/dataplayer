<script setup lang="ts">
import { computed } from "vue"

import { renderProse } from "@/features/content/markdown/render"
import RichBlock from "@/features/content/markdown/RichBlock.vue"

import { splitStreamingDocument } from "./streaming"

const props = defineProps<{ text: string }>()
const blocks = computed(() => splitStreamingDocument(props.text).map((block) =>
  block.type === "prose" ? { ...block, html: renderProse(block.content) } : block
))
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- the prose is rendered and sanitised by
  features/content/markdown/render.ts, the one place that does it. -->
  <div
    class="chat-markdown"
    data-testid="ai-markdown"
  >
    <template
      v-for="(block, index) in blocks"
      :key="`${block.type}-${String(index)}`"
    >
      <div
        v-if="block.type === 'prose'"
        class="chat-markdown__prose"
        v-html="block.html"
      />
      <div
        v-else-if="block.type === 'pending-fence'"
        class="chat-markdown__pending"
        data-testid="ai-open-fence"
      >
        Waiting for the {{ block.language || "code" }} block…
      </div>
      <RichBlock
        v-else
        :block="block"
      />
    </template>
  </div>
</template>

<style scoped>
.chat-markdown { min-width: 0; color: var(--dp-text-strong); }
.chat-markdown__prose :deep(:first-child) { margin-top: 0; }
.chat-markdown__prose :deep(:last-child) { margin-bottom: 0; }
.chat-markdown__prose :deep(table) { display: block; max-width: 100%; overflow: auto; border-collapse: collapse; }
.chat-markdown__prose :deep(th), .chat-markdown__prose :deep(td) { padding: var(--dp-space-1) var(--dp-space-2); border: 1px solid var(--dp-border); }
.chat-markdown__pending { min-height: 72px; padding: var(--dp-space-3); border: 1px solid var(--dp-border-faint); border-radius: var(--dp-radius-panel); background: var(--dp-hover); color: var(--dp-text-muted); }
</style>
