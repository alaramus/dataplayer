/**
 * The Markdown parser, and the two places sanitising hooks into it.
 *
 * Raw HTML is cleaned as its token is rendered, before it can be concatenated
 * with anything the renderer itself produced; the assembled string is cleaned
 * again by the caller. See D50.
 */
import markdownItKatex from "@vscode/markdown-it-katex"
import MarkdownIt from "markdown-it"
import markdownItTaskLists from "markdown-it-task-lists"

import { sanitizeDocument, sanitizeFragment } from "@/features/content/markdown/sanitize"
import type { SanitizeOptions } from "@/features/content/markdown/sanitize"

type Parser = InstanceType<typeof MarkdownIt>
type Plugin = (parser: Parser, options?: Record<string, unknown>) => void

// The plugin ships as CommonJS, so its default export may be nested.
const katexPlugin =
  (markdownItKatex as unknown as { default?: Plugin }).default ??
  (markdownItKatex as unknown as Plugin)

const parser = new MarkdownIt({ html: true, breaks: false, linkify: true })
  .use(katexPlugin, { blockClass: "markdown-block__math" })
  .use(markdownItTaskLists as Plugin, { enabled: false, label: true })

parser.renderer.rules.html_block = (tokens, index) =>
  sanitizeFragment(tokens[index]?.content ?? "")
parser.renderer.rules.html_inline = (tokens, index) =>
  sanitizeFragment(tokens[index]?.content ?? "")

/** One prose block, rendered and sanitised, ready for `v-html`. */
export function renderProse(content: string, options: SanitizeOptions = {}): string {
  return sanitizeDocument(parser.render(content), options)
}
