import type { ComputedRef } from "vue"

import type { Tone } from "@/shared/ui/tokens"

/**
 * Something that will not resolve itself until a person deals with it (D115).
 *
 * Domain-free on purpose: the sheet draws these without knowing whether one is
 * a request for access, a job that never finished or a connection that stopped
 * answering. A feature turns its own unfinished business into these, and the
 * sheet is not edited when a kind is added.
 */
export interface AttentionItem {
  id: string
  tone: Tone
  title: string
  detail: string
  /** The steps behind it, one to a line: each link of a pipeline's run. */
  lines?: string[]
  at: number
  /** The one thing to do about it, offered beside it. */
  action: { label: string; run: () => void } | null
  /**
   * Present only where waving it away is honest. A failed job is news and can
   * go; a request for access cannot, because the row is still waiting.
   */
  dismiss: (() => void) | null
}

/** What a feature exports so its unfinished business reaches the sheet. */
export type AttentionSource = () => ComputedRef<AttentionItem[]>

/** Worst first, then newest: what is broken outranks what is merely waiting. */
const ORDER: Record<Tone, number> = { error: 0, warning: 1, info: 2, success: 3 }

export function ranked(items: AttentionItem[]): AttentionItem[] {
  return [...items].sort((a, b) => ORDER[a.tone] - ORDER[b.tone] || b.at - a.at)
}
