import type { ConversationMessagePublic } from "@/client"
import { t } from "@/shared/i18n"

/** One place in a conversation worth coming back to. */
export interface OutlineMark {
  id: string
  /** The first line of what was asked there, short enough for a tooltip. */
  label: string
}

const MAX_LABEL = 80

function firstLine(content: string): string {
  const line = content.split("\n").map((part) => part.trim()).find(Boolean) ?? ""
  if (line === "") return t("ai.outline.message")
  return line.length > MAX_LABEL ? `${line.slice(0, MAX_LABEL - 1)}…` : line
}

/**
 * The contents of a conversation: what the person asked, in order.
 *
 * Questions only. An answer belongs to the question above it, and marking both
 * would double a list whose whole point is to be read at a glance.
 */
export function outlineMarks(messages: ConversationMessagePublic[]): OutlineMark[] {
  return messages
    .filter((message) => message.role === "user")
    .map((message) => ({ id: message.id, label: firstLine(message.content) }))
}

/**
 * Which mark the reader is at, given where each one sits and how far down the
 * transcript is scrolled.
 *
 * The last one at or above the top of the view, so a question stays current
 * while its answer is being read. Before the first, the first one.
 */
export function markAt(
  offsets: { id: string; top: number }[],
  scrollTop: number
): string | null {
  let current: string | null = offsets[0]?.id ?? null
  for (const offset of offsets) {
    // A few pixels of slack: scrolling a mark to the top lands a hair above it.
    if (offset.top <= scrollTop + 8) current = offset.id
  }
  return current
}
