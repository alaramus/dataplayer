<script setup lang="ts">
import { jsonParseLinter } from "@codemirror/lang-json"
import { syntaxHighlighting } from "@codemirror/language"
import { autocompletion } from "@codemirror/autocomplete"
import type {
  CompletionContext,
  CompletionResult,
  CompletionSource,
} from "@codemirror/autocomplete"
import { type Diagnostic, linter } from "@codemirror/lint"
import { Compartment, EditorState, type Extension, Prec } from "@codemirror/state"
import { EditorView, keymap } from "@codemirror/view"
import { isolateHistory } from "@codemirror/commands"
import { basicSetup } from "codemirror"
import { onBeforeUnmount, onMounted, ref, watch } from "vue"

import { syntaxColours } from "@/features/content/highlight"
import { languageFor } from "@/features/content/language"

const props = withDefaults(
  defineProps<{
    modelValue: string
    filename: string
    languageHint?: string | null
    validation?: "json" | "jsonl" | null
    readonly?: boolean
    /** Whether a line too long for the width continues on the next one. */
    wrap?: boolean
    /**
     * What this editor may offer to write, and what is worth marking.
     *
     * Both are the caller's knowledge: an editor of a file has neither, and a
     * console has both from the source its document is bound to (D65).
     */
    suggestions?: { label: string; detail: string }[]
    marks?: { from: number; to: number; severity: "warning" | "error"; message: string }[]
  }>(),
  {
    languageHint: null,
    validation: null,
    readonly: false,
    wrap: false,
    suggestions: () => [],
    marks: () => [],
  }
)

const emit = defineEmits<{
  "update:modelValue": [value: string]
  /**
   * Where the caret is, or what is selected.
   *
   * A caller that has to know which statement somebody is standing in cannot
   * ask the DOM: the editor owns its own selection.
   */
  "update:selection": [selection: { from: number; to: number }]
  /**
   * The two commands a keyboard reaches inside the editor.
   *
   * Bound here rather than on a container: CodeMirror's own keymap answers
   * Mod-Enter first, so a listener outside would never hear it. What they
   * mean is the caller's business.
   */
  run: []
  "run-script": []
}>()

const host = ref<HTMLElement | null>(null)
const languageName = ref("Plain text")
const languageSlot = new Compartment()
const permissionSlot = new Compartment()
const validationSlot = new Compartment()
const wrapSlot = new Compartment()
const completionSlot = new Compartment()
const marksSlot = new Compartment()
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

function wrapExtension(): Extension {
  return props.wrap ? EditorView.lineWrapping : []
}

/**
 * What the caller offers, beside whatever the language itself completes.
 *
 * Nothing is invented here: the words come from the source, and a word already
 * being typed narrows them the way CodeMirror does everywhere.
 */
function completionExtension(): Extension {
  /**
   * The words this editor offers, from two places at once.
   *
   * The caller's — schemas, relations, columns, parameters — and whatever the
   * language itself completes, which for SQL is its keywords. Asked for here
   * rather than left to the default source because the two have to appear in
   * one list, and a qualified name and a keyword do not start at the same
   * place in the text.
   */
  async function offer(context: CompletionContext): Promise<CompletionResult | null> {
    const dotted = context.matchBefore(/[\w.:]+/)
    const plain = context.matchBefore(/[\w:]+/)
    const qualifying = dotted !== null && dotted.text.includes(".")
    console.warn("DP-OFFER", props.suggestions.length, JSON.stringify(dotted?.text ?? null), qualifying)

    if (qualifying) {
      // Inside `schema.rel`: a keyword would be nonsense here, so only the
      // caller's qualified names are offered.
      const options = props.suggestions
        .filter((suggestion) => suggestion.label.startsWith(dotted.text.split(".")[0] + "."))
        .map((suggestion) => ({ label: suggestion.label, detail: suggestion.detail }))
      return options.length === 0
        ? null
        : { from: dotted.from, options, validFor: /^[\w.:]*$/ }
    }

    const from = plain?.from ?? context.pos
    if (plain === null && !context.explicit) return null
    const options = props.suggestions
      .filter((suggestion) => !suggestion.label.includes("."))
      .map((suggestion) => ({ label: suggestion.label, detail: suggestion.detail }))

    // Whatever the language would have offered, at the same word.
    const language = context.state.languageDataAt<CompletionSource>(
      "autocomplete",
      context.pos
    )
    for (const source of language) {
      if (typeof source !== "function") continue
      const answered = await source(context)
      if (answered === null || answered.from !== from) continue
      options.push(
        ...answered.options.map((option) => ({
          label: option.label,
          detail: option.detail ?? "keyword",
        }))
      )
    }
    // Without the dot: typing one means another question — which relations
    // does that schema hold — and a wider `validFor` would keep answering the
    // old one out of the list already on screen.
    return options.length === 0 ? null : { from, options, validFor: /^[\w:]*$/ }
  }

  // At the highest precedence, so this is the source the one autocompletion
  // basicSetup installed actually asks.
  return Prec.highest(autocompletion({ override: [offer] }))
}

/** The caller's marks, which never block anything: they are only marks. */
function marksExtension(): Extension {
  return linter(() =>
    props.marks.map((mark) => ({
      from: mark.from,
      to: mark.to,
      severity: mark.severity,
      message: mark.message,
    }))
  )
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
        // Before basicSetup: an earlier extension wins the facet, and what
        // basicSetup carries is a light-theme palette.
        syntaxHighlighting(syntaxColours),
        basicSetup,
        languageSlot.of([]),
        permissionSlot.of(permissionExtensions()),
        validationSlot.of(validationExtension()),
        wrapSlot.of(wrapExtension()),
        completionSlot.of(completionExtension()),
        EditorState.languageData.of((_state, pos) => {
          console.warn("DP-DIRECT-LD", pos)
          return []
        }),
        marksSlot.of(marksExtension()),
        EditorView.contentAttributes.of({
          "aria-label": `${props.filename} source`,
          spellcheck: "false",
        }),
        // Above basicSetup: Mod-Enter is `insertBlankLine` in the default
        // keymap, and a command bound below it would never be reached.
        Prec.highest(
          keymap.of([
            {
              key: "Mod-Enter",
              run: () => {
                emit("run")
                return true
              },
            },
            {
              key: "Mod-Shift-Enter",
              run: () => {
                emit("run-script")
                return true
              },
            },
          ])
        ),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) emit("update:modelValue", update.state.doc.toString())
          if (update.selectionSet || update.docChanged) {
            const range = update.state.selection.main
            emit("update:selection", { from: range.from, to: range.to })
          }
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
          // Written out in full, and with `.cm-editor` in it, because
          // CodeMirror's own rule for this is five selectors deep and a
          // shorter one loses to it however late it is added. Focused and
          // unfocused both: the editor draws the selection itself while it
          // has focus and hands it to the browser when it does not, and a
          // dark theme was falling back to a pale lilac wash that took the
          // letters with it.
          "&.cm-editor.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground":
            {
              background: "var(--dp-text-selection)",
            },
          "&.cm-editor > .cm-scroller > .cm-selectionLayer .cm-selectionBackground":
            {
              background: "var(--dp-text-selection)",
            },
          "&.cm-editor .cm-content ::selection": {
            background: "var(--dp-text-selection)",
          },
          // The match a search is standing on, which is drawn over the
          // selection and has to stay legible against it.
          ".cm-selectionMatch, .cm-searchMatch": {
            backgroundColor: "var(--dp-selected)",
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
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value },
      // Text that arrived from outside is its own step in the history:
      // formatting, or taking somebody else's version, is not a continuation
      // of what was being typed, and one undo must take exactly it back (D65).
      annotations: isolateHistory.of("full"),
    })
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

watch(
  () => props.wrap,
  () => view?.dispatch({ effects: wrapSlot.reconfigure(wrapExtension()) })
)

watch(
  () => props.suggestions,
  () => view?.dispatch({ effects: completionSlot.reconfigure(completionExtension()) })
)

watch(
  () => props.marks,
  () => view?.dispatch({ effects: marksSlot.reconfigure(marksExtension()) })
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
