<script setup lang="ts">
import { defineAsyncComponent } from "vue"

import AgentBlock from "./AgentBlock.vue"
import type { RichDocumentBlock } from "./blocks"
import DeferredBlock from "./DeferredBlock.vue"

/**
 * One block of Markdown that is not prose — a diagram, a chart, a drawing,
 * code, an agent's card, or a block too large to draw — drawn the same in a
 * document and in the agent's answer (D50, D138). A new kind of block is
 * added here once. Prose stays with the caller: a document numbers its
 * headings and a chat does not.
 *
 * The heavy renderers are fetched when the first block of their kind is, and
 * a block mounts when it is about to be seen, unless `eager`: an export needs
 * every block drawn at once.
 */
withDefaults(defineProps<{ block: RichDocumentBlock; eager?: boolean }>(), { eager: false })

const CodeFence = defineAsyncComponent(() => import("./CodeFence.vue"))
const EchartsBlock = defineAsyncComponent(() => import("./EchartsBlock.vue"))
const MermaidBlock = defineAsyncComponent(() => import("./MermaidBlock.vue"))
const SvgBlock = defineAsyncComponent(() => import("./SvgBlock.vue"))
</script>

<template>
  <DeferredBlock
    v-if="block.type === 'mermaid'"
    :eager="eager"
  >
    <MermaidBlock :code="block.code" />
  </DeferredBlock>
  <DeferredBlock
    v-else-if="block.type === 'echarts'"
    :eager="eager"
  >
    <EchartsBlock :code="block.code" />
  </DeferredBlock>
  <DeferredBlock
    v-else-if="block.type === 'svg'"
    :eager="eager"
  >
    <SvgBlock :code="block.code" />
  </DeferredBlock>
  <DeferredBlock
    v-else-if="block.type === 'code'"
    :eager="eager"
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
    class="rich-block__oversized"
    data-testid="markdown-oversized"
  >
    This {{ block.language }} block is too large to draw.
  </p>
</template>

<style scoped>
.rich-block__oversized {
  margin: 12px 0;
  color: var(--dp-text-muted);
  font-size: 12px;
}
</style>
