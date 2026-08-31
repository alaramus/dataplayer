<script setup lang="ts">
/**
 * One callout an agent wrote: a summary, a decision, a risk, a checked result.
 *
 * The fence is ordinary Markdown everywhere else, so nothing is lost by reading
 * it as a card here — and the colour is what the card means. See D50.
 */
import { computed } from "vue"

import { AGENT_LOOKS, readAgentBlock } from "@/features/content/markdown/agent"
import type { AgentKind } from "@/features/content/markdown/agent"
import { copySource } from "@/features/content/markdown/blockActions"
import BlockChrome from "@/features/content/markdown/BlockChrome.vue"
import { renderProse } from "@/features/content/markdown/render"
import { AppCopyButton, useToast } from "@/shared/ui"

const props = defineProps<{ kind: AgentKind; code: string }>()

const toast = useToast()
const look = computed(() => AGENT_LOOKS[props.kind])
const content = computed(() => readAgentBlock(props.code))
const body = computed(() => (content.value.body === "" ? "" : renderProse(content.value.body)))

async function copy() {
  await copySource(props.code)
  toast.success("Callout copied")
}
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- the body is rendered and sanitised by
  features/content/markdown/render.ts, the one place that does it. -->
  <BlockChrome
    :label="look.label"
    :icon="look.icon"
    :accent="look.accent"
  >
    <template #actions>
      <AppCopyButton
        tooltip="Copy this callout"
        data-testid="agent-copy"
        @click="copy"
      />
    </template>

    <div
      class="agent-block"
      :data-testid="`agent-${kind}`"
    >
      <dl
        v-if="content.fields.length > 0"
        class="agent-block__fields"
      >
        <template
          v-for="field in content.fields"
          :key="field.key"
        >
          <dt>{{ field.key }}</dt>
          <dd>{{ field.value }}</dd>
        </template>
      </dl>
      <div
        v-if="body"
        class="agent-block__body"
        v-html="body"
      />
    </div>
  </BlockChrome>
</template>

<style scoped>
.agent-block {
  padding: 10px 14px;
}
.agent-block__fields {
  display: grid;
  grid-template-columns: minmax(70px, max-content) 1fr;
  gap: 4px 12px;
  margin: 0;
}
.agent-block__fields dt {
  color: var(--dp-text-muted);
  font-size: 11px;
  text-transform: uppercase;
}
.agent-block__fields dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.agent-block__body {
  line-height: 1.6;
}
.agent-block__fields + .agent-block__body {
  margin-top: 8px;
}
.agent-block__body :deep(p:first-child) {
  margin-top: 0;
}
.agent-block__body :deep(p:last-child) {
  margin-bottom: 0;
}
.agent-block__body :deep(code) {
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--dp-hover);
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}
</style>
