import { HighlightStyle } from "@codemirror/language"
import { tags } from "@lezer/highlight"

/**
 * One syntax palette for every place this application shows code.
 *
 * CodeMirror's own `defaultHighlightStyle` is a light-theme palette — keywords
 * come out as dark purple on near-black, which is what the dark theme was
 * showing. The colours here are theme tokens, so one style serves both themes
 * and nothing has to be rebuilt when the theme changes.
 */
export const syntaxColours = HighlightStyle.define([
  { tag: [tags.keyword, tags.modifier, tags.controlKeyword], color: "var(--dp-code-keyword)" },
  { tag: [tags.name, tags.deleted, tags.character, tags.propertyName], color: "var(--dp-text)" },
  { tag: [tags.function(tags.variableName), tags.labelName], color: "var(--dp-code-function)" },
  { tag: [tags.definition(tags.name), tags.separator], color: "var(--dp-text)" },
  {
    tag: [tags.typeName, tags.className, tags.namespace, tags.changed, tags.annotation],
    color: "var(--dp-code-type)",
  },
  { tag: [tags.number, tags.bool, tags.null, tags.atom], color: "var(--dp-code-number)" },
  { tag: [tags.string, tags.special(tags.string), tags.regexp], color: "var(--dp-code-string)" },
  { tag: [tags.operator, tags.operatorKeyword, tags.escape], color: "var(--dp-code-operator)" },
  { tag: [tags.meta, tags.comment], color: "var(--dp-code-comment)", fontStyle: "italic" },
  { tag: tags.strong, fontWeight: "bold" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strikethrough, textDecoration: "line-through" },
  { tag: tags.link, color: "var(--dp-link)", textDecoration: "underline" },
  { tag: tags.heading, color: "var(--dp-code-keyword)", fontWeight: "bold" },
  { tag: tags.invalid, color: "var(--dp-content-error)" },
])
