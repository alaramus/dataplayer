<script setup lang="ts">
import { appIcons } from "@/shared/ui"
/** One `svg` fence, through the SVG profile with scripting forbidden. See D50. */
import { computed, ref } from "vue"

import { copySource, saveSvg } from "@/features/content/markdown/blockActions"
import { sanitizeSvg } from "@/features/content/markdown/sanitize"
import BlockChrome from "@/features/content/markdown/BlockChrome.vue"
import { t } from "@/shared/i18n"
import { AppCopyButton, AppIconButton, useToast } from "@/shared/ui"

const props = defineProps<{ code: string }>()

/** The format's name, which no language translates. */
const label = "svg"

const toast = useToast()
const showSource = ref(false)
const svg = computed(() => sanitizeSvg(props.code))

async function copy() {
  await copySource(props.code)
  toast.success(t("content.markdown.svg.copied"))
}

function download() {
  // What is saved is what was shown: the sanitised markup, not the fence.
  saveSvg(svg.value, "image.svg")
}
</script>

<template>
  <!-- eslint-disable vue/no-v-html -- every string below comes from
  features/content/markdown/sanitize.ts, which exists for exactly this and is
  covered by sanitize.spec.ts. Rendering a document without v-html would mean
  building the DOM by hand from the same HTML. -->
  <BlockChrome :label="label">
    <template #actions>
      <AppIconButton
        :icon="showSource ? appIcons.image : appIcons.code"
        :tooltip="showSource ? t('content.markdown.svg.show_picture') : t('content.markdown.svg.show_source')"
        data-testid="svg-source-toggle"
        @click="showSource = !showSource"
      />
      <AppIconButton
        :icon="appIcons.download"
        :tooltip="t('content.markdown.svg.save')"
        data-testid="svg-download"
        @click="download"
      />
      <AppCopyButton
        :tooltip="t('content.markdown.svg.copy')"
        data-testid="svg-copy"
        @click="copy"
      />
    </template>

    <pre
      v-if="showSource"
      class="svg-block__source"
      data-testid="svg-source"
    >{{ code }}</pre>
    <div
      v-else
      class="svg-block__figure"
      data-testid="svg-figure"
      v-html="svg"
    />
  </BlockChrome>
</template>

<style scoped>
.svg-block__figure {
  display: grid;
  place-items: center;
  min-height: 120px;
  padding: var(--dp-space-4);
}
.svg-block__figure :deep(svg) {
  display: block;
  max-width: 100%;
  height: auto;
}
.svg-block__source {
  margin: 0;
  padding: var(--dp-space-3);
  overflow-x: auto;
  color: var(--dp-text);
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-sm);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
