import type { ContentsPlace, JobPublic } from "@/client"

import type { AnswerState } from "./answer"

/**
 * A search inside files, as a job (S7): which connections of an answer can
 * be asked, what the job's row says of it, and how long its matches are held.
 *
 * The words live in the server's memory and, for "Search again", in this
 * tab's memory only (`shared/search/contentsWords.ts`), never in storage.
 */

export const CONTENTS_KIND = "search.contents"

/** What Recent says of a search whose matches the server has let go. */
export const NO_LONGER_HELD = "Its matches are no longer held"

export interface ContentsChoice {
  connectorId: string
  name: string
}

/** The connections of an answer that can be searched inside, in the plan's order. */
export function contentsChoices(state: AnswerState): ContentsChoice[] {
  const chosen = new Map<string, string>()
  for (const { planned } of state.cells) {
    if (!planned.contents || planned.connector_id === null) continue
    if (!chosen.has(planned.connector_id)) chosen.set(planned.connector_id, planned.group.title)
  }
  return [...chosen].map(([connectorId, name]) => ({ connectorId, name }))
}

export { contentsWordsOf, rememberContentsWords } from "@/shared/search/contentsWords"

interface Counts {
  connections: number
  searched: number
  found: number
  heldSeconds: number
}

/** What the job's row counts; never its words (S7). */
export function contentsCounts(job: Pick<JobPublic, "kind" | "parameters">): Counts | null {
  if (job.kind !== CONTENTS_KIND) return null
  const values = job.parameters ?? {}
  const number = (key: string) => {
    const value = values[key]
    return typeof value === "number" && Number.isFinite(value) ? value : 0
  }
  return {
    connections: number("connections"),
    searched: number("searched"),
    found: number("found"),
    heldSeconds: number("held_seconds"),
  }
}

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString()} ${count === 1 ? one : many}`
}

/** "1 of 2 connections · 3 found": what the footer measures it by. */
export function contentsMeasure(counts: Counts): string {
  return `${String(counts.searched)} of ${plural(counts.connections, "connection", "connections")} · ${counts.found.toLocaleString()} found`
}

/** When the server lets its matches go, or null when it has not ended. */
export function heldUntil(job: Pick<JobPublic, "kind" | "parameters" | "finished_at">): number | null {
  const counts = contentsCounts(job)
  const ended = Date.parse(job.finished_at ?? "")
  if (counts === null || !Number.isFinite(ended)) return null
  return ended + counts.heldSeconds * 1000
}

export function contentsExpired(
  job: Pick<JobPublic, "kind" | "parameters" | "finished_at">,
  now: number
): boolean {
  const until = heldUntil(job)
  return until !== null && now >= until
}

const SKIPPED: Record<string, string> = {
  switched_off: "Switched off",
  cannot_search: "Can't be searched inside files",
  not_asked: "Not searched",
}

/** What one chosen connection says, or null when it simply answered. */
export function placeSentence(place: ContentsPlace): string | null {
  switch (place.status) {
    case "waiting":
      return "Waiting"
    case "complete":
      return place.notice
    case "stopped":
      return place.notice ?? "Stopped"
    case "failed":
      return place.message ?? "Could not be searched"
    case "skipped":
      return place.notice ?? SKIPPED[place.reason ?? ""] ?? "Not searched"
  }
}
