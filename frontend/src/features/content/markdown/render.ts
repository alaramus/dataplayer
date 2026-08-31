/**
 * The Markdown parser, and the two places sanitising hooks into it.
 *
 * Raw HTML is cleaned as its token is rendered, before it can be concatenated
 * with anything the renderer itself produced; the assembled string is cleaned
 * again by the caller. See D50.
 */
import markdownItKatex from "@vscode/markdown-it-katex"
import MarkdownIt from "markdown-it"
import type { Env } from "markdown-it"
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

export interface DocumentHeading {
  id: string
  title: string
  level: number
}

export interface ProseOutline {
  headings: DocumentHeading[]
  /** Heading ids in the order each prose block's renderer consumes them. */
  blockHeadingIds: string[][]
}

interface RenderEnvironment extends Env {
  headingIds: string[]
  headingIndex: number
  sanitizeOptions: SanitizeOptions
}

export interface RenderProseOptions extends SanitizeOptions {
  headingIds?: string[]
}

function environment(value: unknown): RenderEnvironment {
  const candidate = value as Partial<RenderEnvironment> | undefined
  return {
    headingIds: candidate?.headingIds ?? [],
    headingIndex: candidate?.headingIndex ?? 0,
    sanitizeOptions: candidate?.sanitizeOptions ?? {},
  }
}

parser.renderer.rules.html_block = (tokens, index, _options, env) =>
  sanitizeFragment(tokens[index]?.content ?? "", environment(env).sanitizeOptions)
parser.renderer.rules.html_inline = (tokens, index, _options, env) =>
  sanitizeFragment(tokens[index]?.content ?? "", environment(env).sanitizeOptions)
parser.renderer.rules.heading_open = (tokens, index, options, env, self) => {
  const state = environment(env)
  const id = state.headingIds[state.headingIndex]
  if (id !== undefined) {
    tokens[index]?.attrSet("id", id)
    tokens[index]?.attrSet("tabindex", "-1")
    const mutableEnvironment = env as unknown as RenderEnvironment
    mutableEnvironment.headingIndex = state.headingIndex + 1
  }
  return self.renderToken(tokens, index, options)
}

function slugifyHeading(value: string): string {
  return (
    value
      .toLocaleLowerCase()
      .trim()
      .replace(/<[^>]+>/g, "")
      .replace(/[^\p{L}\p{N}]+/gu, "-")
      .replace(/^-+|-+$/g, "") || "section"
  )
}

function headingIdGenerator(): (title: string) => string {
  const used = new Set<string>()
  const suffixes = new Map<string, number>()
  return (title) => {
    const base = slugifyHeading(title)
    if (!used.has(base)) {
      used.add(base)
      suffixes.set(base, 2)
      return base
    }
    let suffix = suffixes.get(base) ?? 2
    let candidate = `${base}-${String(suffix)}`
    while (used.has(candidate)) {
      suffix += 1
      candidate = `${base}-${String(suffix)}`
    }
    used.add(candidate)
    suffixes.set(base, suffix + 1)
    return candidate
  }
}

function headingTitle(
  token:
    | {
        content?: string
        children?: ReadonlyArray<{ type: string; content: string }> | null
      }
    | undefined
): string {
  const visible = (token?.children ?? [])
    .map((child) => {
      if (["text", "code_inline", "image"].includes(child.type)) return child.content
      if (["softbreak", "hardbreak"].includes(child.type)) return " "
      return ""
    })
    .join("")
    .trim()
  return (
    visible ||
    (token?.content ?? "section")
      .replace(/<[^>]+>/g, "")
      .replace(/[*_`~]/g, "")
      .trim()
  )
}

/** The outline for the exact prose blocks that will be rendered below it. */
export function outlineProse(contents: string[]): ProseOutline {
  const headings: DocumentHeading[] = []
  const blockHeadingIds: string[][] = []
  const nextId = headingIdGenerator()
  for (const content of contents) {
    const tokens = parser.parse(content, {})
    const ids: string[] = []
    tokens.forEach((token, index) => {
      if (token.type !== "heading_open") return
      const title = headingTitle(tokens[index + 1])
      const id = nextId(title)
      ids.push(id)
      headings.push({ id, title, level: Number(token.tag.slice(1)) })
    })
    blockHeadingIds.push(ids)
  }
  return { headings, blockHeadingIds }
}

/** One prose block, rendered and sanitised, ready for `v-html`. */
export function renderProse(content: string, options: RenderProseOptions = {}): string {
  const { headingIds = [], ...sanitizeOptions } = options
  const env: RenderEnvironment = { headingIds, headingIndex: 0, sanitizeOptions }
  return sanitizeDocument(parser.render(content, env), sanitizeOptions)
}
