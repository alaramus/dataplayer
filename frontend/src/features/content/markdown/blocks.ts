/**
 * Split a document at fence boundaries before anything parses it.
 *
 * A diagram, a chart or an SVG must never reach the Markdown parser: they are
 * their own languages, they have their own ceilings, and they are drawn by
 * components that mount only when they are seen. What is left between fences is
 * prose, and only that is Markdown. See D50.
 */

import { agentKindOf } from "@/features/content/markdown/agent"
import type { AgentKind } from "@/features/content/markdown/agent"

/** One fence this large is refused rather than drawn. */
export const MAX_RICH_BLOCK_CHARS = 250_000

export type DocumentBlock =
  | { type: "prose"; content: string }
  | { type: "mermaid"; code: string }
  | { type: "echarts"; code: string }
  | { type: "svg"; code: string }
  | { type: "code"; language: string; code: string }
  | { type: "agent"; kind: AgentKind; code: string }
  | { type: "oversized"; language: string }

/** Every block but prose: what `RichBlock` draws. */
export type RichDocumentBlock = Exclude<DocumentBlock, { type: "prose" }>

const FENCE_OPEN = /^ {0,3}(`{3,})(.*)$/
const FENCE_CLOSE = /^ {0,3}(`{3,})\s*$/

function fenceBlock(language: string, code: string): DocumentBlock {
  if (code.length > MAX_RICH_BLOCK_CHARS) {
    return { type: "oversized", language: language || "code" }
  }
  const agent = agentKindOf(language)
  if (agent !== null) return { type: "agent", kind: agent, code }
  if (language === "mermaid") return { type: "mermaid", code }
  if (language === "echarts") return { type: "echarts", code }
  if (language === "svg") return { type: "svg", code }
  return { type: "code", language, code }
}

export function splitDocument(text: string): DocumentBlock[] {
  const blocks: DocumentBlock[] = []
  let prose: string[] = []
  let fence: string[] = []
  let language = ""
  let ticks = 0
  let inFence = false

  function flushProse() {
    const content = prose.join("\n")
    prose = []
    if (content.trim()) blocks.push({ type: "prose", content })
  }

  for (const line of text.split("\n")) {
    if (!inFence) {
      const opening = FENCE_OPEN.exec(line)
      if (opening) {
        flushProse()
        inFence = true
        ticks = opening[1]?.length ?? 3
        language = (opening[2] ?? "").trim().toLowerCase().split(/\s+/)[0] ?? ""
        fence = []
      } else {
        prose.push(line)
      }
      continue
    }

    const closing = FENCE_CLOSE.exec(line)
    if (closing && (closing[1]?.length ?? 0) >= ticks) {
      blocks.push(fenceBlock(language, fence.join("\n")))
      inFence = false
      fence = []
      language = ""
      continue
    }
    fence.push(line)
  }

  if (inFence) {
    // A document cut at its ceiling can end inside a fence. Half a diagram is
    // not a diagram, so what was collected is shown as the text it is.
    blocks.push({ type: "code", language, code: fence.join("\n") })
  } else {
    flushProse()
  }

  return blocks
}
