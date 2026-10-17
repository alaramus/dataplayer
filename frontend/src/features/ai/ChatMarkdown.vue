<script setup lang="ts">
import { computed } from "vue"

import ProseBlock from "@/features/content/markdown/ProseBlock.vue"
import { renderProse } from "@/features/content/markdown/render"
import RichBlock from "@/features/content/markdown/RichBlock.vue"
import { t } from "@/shared/i18n"

import { splitStreamingDocument } from "./streaming"

const props = defineProps<{ text: string }>()
const blocks = computed(() => splitStreamingDocument(props.text).map((block) =>
  block.type === "prose" ? { ...block, html: renderProse(block.content) } : block
))
</script>

<template>
  <div
    class="chat-markdown"
    data-testid="ai-markdown"
  >
    <template
      v-for="(block, index) in blocks"
      :key="`${block.type}-${String(index)}`"
    >
      <ProseBlock
        v-if="block.type === 'prose'"
        class="chat-markdown__prose"
        :html="block.html"
      />
      <div
        v-else-if="block.type === 'pending-fence'"
        class="chat-markdown__pending"
        data-testid="ai-open-fence"
      >
        {{ block.language ? t('ai.markdown.waiting', { language: block.language }) : t('ai.markdown.waiting_code') }}
      </div>
      <RichBlock
        v-else
        :block="block"
      />
    </template>
  </div>
</template>

<style scoped>
.chat-markdown { min-width: 0; color: var(--dp-text); font-size: var(--dp-prose-font-size); line-height: 1.65; }
/* An answer starts and ends at its own edge, not a heading's margin away. */
.chat-markdown__prose :deep(:first-child) { margin-top: 0; }
.chat-markdown__prose :deep(:last-child) { margin-bottom: 0; }
.chat-markdown__pending { min-height: 72px; padding: var(--dp-space-3); border: 1px solid var(--dp-border-faint); border-radius: var(--dp-radius-panel); background: var(--dp-hover); color: var(--dp-text-muted); }
</style>
