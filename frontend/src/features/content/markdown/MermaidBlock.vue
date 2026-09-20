<script setup lang="ts">
/**
 * One `mermaid` fence. Mermaid runs at `securityLevel: "strict"`, so its own
 * HTML labels never appear, and what it draws is sanitised as SVG before it
 * reaches the document. See D50.
 */
import { onBeforeUnmount, ref, watch } from "vue"

import { copySource, saveSvg } from "@/features/content/markdown/blockActions"
import { renderDiagram } from "@/features/content/markdown/mermaid"
import { sanitizeSvg } from "@/features/content/markdown/sanitize"
import BlockChrome from "@/features/content/markdown/BlockChrome.vue"
import { useThemeStore } from "@/stores/theme"
import { AppCopyButton, AppIconButton, useToast } from "@/shared/ui"

const props = defineProps<{ code: string }>()

const theme = useThemeStore()
const toast = useToast()
const svg = ref("")
const failure = ref("")
let attempt = 0

async function draw() {
  const current = ++attempt
  failure.value = ""
  try {
    const drawn = await renderDiagram(props.code, theme.dark)
    if (current !== attempt) return
    const cleaned = sanitizeSvg(drawn.svg, { allowStyles: true })
    // An empty answer is a failure that would otherwise look like a blank box.
    if (!cleaned.includes("<svg")) throw new Error("This diagram came back empty")
    svg.value = cleaned
  } catch (cause) {
    if (current !== attempt) return
    svg.value = ""
    failure.value = cause instanceof Error ? cause.message : "This diagram could not be drawn"
  }
}

async function copy() {
  await copySource(props.code)
  toast.success("Diagram source copied")
}

function download() {
  saveSvg(svg.value, "diagram.svg")
}

watch([() => props.code, () => theme.dark], () => void draw(), { immediate: true })
onBeforeUnmount(() => {
  attempt += 1
})
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- every string below comes from
  features/content/markdown/sanitize.ts, which exists for exactly this and is
  covered by sanitize.spec.ts. Rendering a document without v-html would mean
  building the DOM by hand from the same HTML. -->
  <BlockChrome label="mermaid">
    <template #actions>
      <AppIconButton
        v-if="!failure"
        icon="download"
        tooltip="Save this diagram as SVG"
        data-testid="mermaid-download"
        @click="download"
      />
      <AppCopyButton
        tooltip="Copy the diagram source"
        data-testid="mermaid-copy"
        @click="copy"
      />
    </template>

    <p
      v-if="failure"
      class="mermaid-block__failure"
      data-testid="mermaid-failure"
    >
      {{ failure }}
    </p>
    <div
      v-else
      class="mermaid-block__figure"
      data-testid="mermaid-figure"
      v-html="svg"
    />
  </BlockChrome>
</template>

<style scoped>
.mermaid-block__figure {
  padding: var(--dp-space-3);
}
.mermaid-block__figure :deep(svg) {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
}
.mermaid-block__failure {
  margin: 0;
  padding: var(--dp-space-3);
  color: var(--dp-text-muted);
  font-size: 12px;
}
</style>
