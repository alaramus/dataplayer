<script setup lang="ts">
import { jsonParseLinter } from "@codemirror/lang-json"
import { type Diagnostic, linter } from "@codemirror/lint"
import { Compartment, EditorState, type Extension } from "@codemirror/state"
import { EditorView } from "@codemirror/view"
import { basicSetup } from "codemirror"
import { onBeforeUnmount, onMounted, ref, watch } from "vue"

import { languageFor } from "@/features/content/language"

const props = withDefaults(
  defineProps<{
    modelValue: string
    filename: string
    languageHint?: string | null
    validation?: "json" | "jsonl" | null
    readonly?: boolean
  }>(),
  {
    languageHint: null,
    validation: null,
    readonly: false,
  }
)

const emit = defineEmits<{
  "update:modelValue": [value: string]
}>()

const host = ref<HTMLElement | null>(null)
const languageName = ref("Plain text")
const languageSlot = new Compartment()
const permissionSlot = new Compartment()
const validationSlot = new Compartment()
let view: EditorView | null = null
let languageRequest = 0

function permissionExtensions(): Extension {
  return [
    EditorState.readOnly.of(props.readonly),
    EditorView.editable.of(!props.readonly),
  ]
}

function jsonLinesDiagnostics(editor: EditorView): Diagnostic[] {
  const diagnostics: Diagnostic[] = []
  for (let number = 1; number <= editor.state.doc.lines; number += 1) {
    const line = editor.state.doc.line(number)
    if (!line.text.trim()) continue
    try {
      JSON.parse(line.text)
    } catch (cause) {
      diagnostics.push({
        from: line.from,
        to: line.to,
        severity: "error",
        source: "JSONL",
        message: cause instanceof SyntaxError ? cause.message : "Invalid JSON value",
      })
    }
  }
  return diagnostics
}

function validationExtension(): Extension {
  if (props.validation === "json") return linter(jsonParseLinter())
  if (props.validation === "jsonl") return linter(jsonLinesDiagnostics)
  return []
}

async function loadLanguage() {
  const editor = view
  if (!editor) return
  const request = ++languageRequest
  const description = languageFor(props.filename, props.languageHint)
  languageName.value = description?.name ?? "Plain text"
  const support = description ? await description.load() : []
  if (view !== editor || request !== languageRequest) return
  editor.dispatch({ effects: languageSlot.reconfigure(support) })
}

onMounted(() => {
  if (!host.value) return
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        languageSlot.of([]),
        permissionSlot.of(permissionExtensions()),
        validationSlot.of(validationExtension()),
        EditorView.contentAttributes.of({
          "aria-label": `${props.filename} source`,
          spellcheck: "false",
        }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) emit("update:modelValue", update.state.doc.toString())
        }),
        EditorView.theme({
          "&": {
            height: "100%",
            color: "var(--dp-text-strong)",
            backgroundColor: "var(--dp-surface)",
            fontSize: "12px",
          },
          ".cm-scroller": {
            fontFamily: 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace',
          },
          ".cm-gutters": {
            color: "var(--dp-text-muted)",
            backgroundColor: "var(--dp-chrome-raised)",
            borderRight: "1px solid var(--dp-border-faint)",
          },
          ".cm-activeLine, .cm-activeLineGutter": {
            backgroundColor: "var(--dp-hover)",
          },
        }),
      ],
    }),
  })
  void loadLanguage()
})

onBeforeUnmount(() => {
  languageRequest += 1
  view?.destroy()
  view = null
})

watch(
  () => props.modelValue,
  (value) => {
    if (!view || view.state.doc.toString() === value) return
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
  }
)

watch(
  () => props.readonly,
  () => view?.dispatch({ effects: permissionSlot.reconfigure(permissionExtensions()) })
)

watch(
  () => props.validation,
  () => view?.dispatch({ effects: validationSlot.reconfigure(validationExtension()) })
)

watch([() => props.filename, () => props.languageHint], () => void loadLanguage())
</script>

<template>
  <div class="code-editor">
    <div
      ref="host"
      class="code-editor__surface"
    />
    <span
      class="code-editor__language"
      data-testid="editor-language"
    >
      {{ languageName }}
    </span>
  </div>
</template>

<style scoped>
.code-editor {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--dp-border-faint);
  border-radius: 4px;
}
.code-editor__surface {
  height: 100%;
}
.code-editor__language {
  position: absolute;
  right: 14px;
  bottom: 8px;
  padding: 2px 6px;
  border: 1px solid var(--dp-border-faint);
  border-radius: 3px;
  background: var(--dp-surface);
  color: var(--dp-text-muted);
  font-size: 10px;
  pointer-events: none;
}
</style>
