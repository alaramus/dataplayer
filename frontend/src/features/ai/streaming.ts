import { splitDocument } from "@/features/content/markdown/blocks"
import type { DocumentBlock } from "@/features/content/markdown/blocks"
import { plainSpeechText } from "@/features/speech/speechText"

export { plainSpeechText }

export type StreamingBlock = DocumentBlock | { type: "pending-fence"; language: string }

/** Keep an unfinished rich fence away from its parser while tokens arrive (D138). */
export function splitStreamingDocument(text: string): StreamingBlock[] {
  const lines = text.split("\n")
  let opened: { ticks: number; language: string; start: number } | null = null
  let offset = 0
  for (const line of lines) {
    const opening = /^ {0,3}(`{3,})(.*)$/.exec(line)
    const closing = /^ {0,3}(`{3,})\s*$/.exec(line)
    if (opened === null && opening !== null) {
      opened = {
        ticks: opening[1]?.length ?? 3,
        language: (opening[2] ?? "").trim().toLowerCase().split(/\s+/)[0] ?? "",
        start: offset,
      }
      offset += line.length + 1
      continue
    }
    if (opened !== null && closing !== null && (closing[1]?.length ?? 0) >= opened.ticks) {
      opened = null
    }
    offset += line.length + 1
  }
  if (opened === null) return splitDocument(text)
  const prefix = text.slice(0, opened.start).replace(/\n$/, "")
  return [...splitDocument(prefix), { type: "pending-fence", language: opened.language }]
}
