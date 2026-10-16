<script setup lang="ts">
/**
 * One code fence, highlighted by the CodeMirror the source editor already
 * carries — read-only, without gutters or an editing surface. There is no
 * second syntax highlighter in this bundle. See D50.
 */
import { syntaxHighlighting, type LanguageDescription } from "@codemirror/language"
import { Compartment, EditorState } from "@codemirror/state"
import { EditorView } from "@codemirror/view"
import { onBeforeUnmount, onMounted, ref, watch } from "vue"

import { copySource } from "@/features/content/markdown/blockActions"
import BlockChrome from "@/features/content/markdown/BlockChrome.vue"
import { syntaxColours } from "@/features/content/highlight"
import { languageFor } from "@/features/content/language"
import { t } from "@/shared/i18n"
import { AppCopyButton, useToast } from "@/shared/ui"

const props = defineProps<{ language: string; code: string }>()

const toast = useToast()
const host = ref<HTMLElement | null>(null)
const languageSlot = new Compartment()
let view: EditorView | null = null
let request = 0

async function loadLanguage() {
  const editor = view
  if (!editor) return
  const current = ++request
  const description: LanguageDescription | null = props.language
    ? languageFor("", props.language)
    : null
  const support = description ? await description.load() : []
  if (view !== editor || current !== request) return
  editor.dispatch({ effects: languageSlot.reconfigure(support) })
}

function mount() {
  if (!host.value) return
  view?.destroy()
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.code,
      extensions: [
        EditorState.readOnly.of(true),
        EditorView.editable.of(false),
        EditorView.lineWrapping,
        syntaxHighlighting(syntaxColours, { fallback: true }),
        languageSlot.of([]),
        EditorView.contentAttributes.of({ "aria-label": t("content.markdown.code.aria"), spellcheck: "false" }),
        EditorView.theme({
          "&": {
            color: "var(--dp-text)",
            backgroundColor: "transparent",
            fontSize: "var(--dp-prose-code-font-size)",
          },
          ".cm-content": { padding: "0" },
          ".cm-scroller": {
            fontFamily: 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace',
          },
        }),
      ],
    }),
  })
  void loadLanguage()
}

async function copy() {
  await copySource(props.code)
  toast.success(t("content.markdown.code.copied"))
}

onMounted(mount)
onBeforeUnmount(() => {
  request += 1
  view?.destroy()
  view = null
})

watch(() => props.code, mount)
watch(() => props.language, () => void loadLanguage())
</script>

<template>
  <BlockChrome :label="language || t('content.markdown.code.label')">
    <template #actions>
      <AppCopyButton
        :tooltip="t('content.markdown.code.copy')"
        data-testid="code-copy"
        @click="copy"
      />
    </template>

    <div
      ref="host"
      class="code-fence__surface"
      data-testid="code-fence"
    />
  </BlockChrome>
</template>

<style scoped>
.code-fence__surface {
  padding: var(--dp-space-2) var(--dp-space-3);
  background: var(--dp-chrome-raised);
}
</style>
