import type { JobPublic } from "@/client"
import { isWorking } from "@/features/services/jobs"
import type { AttentionItem, Notice } from "@/shared/notifications"

import { pipelineRunOf } from "./pipelineRuns"
import type { ProcessRow } from "./presentation"

/**
 * What becomes of a job once it ends (D181): one entry, in one section.
 *
 * Working holds only what runs. An ending is recorded once — in Recent when it
 * did what was asked or was stopped on request, in Needs you when it did not —
 * and the card on screen is that entry arriving, not a record of its own.
 */

/** How long an ended job is still recent, read again from the server after a reload. */
export const RECENT_FOR = 24 * 60 * 60 * 1000

/** The log's id for a job's ending, so it is written once however often it is read. */
export function endingId(jobId: string): string {
  return `job:${jobId}`
}

/** The job an id of `endingId` names, or nothing for any other entry. */
export function jobOfEnding(id: string): string | null {
  return id.startsWith("job:") ? id.slice(4) : null
}

/** The lines of a row beyond what its message already says. */
export function linesBeyond(detail: string, message: string): string[] {
  return detail.split("\n").map((line) => line.trim()).filter((line) => line !== "" && line !== message)
}

export interface EndedEntry {
  id: string
  at: number
  notice: Omit<Notice, "id" | "at" | "seq">
}

/**
 * A job's ending as Recent keeps it, or nothing: a failure waits in Needs you
 * instead, and a job still going is not an ending.
 */
export function endedEntry(job: JobPublic, row: ProcessRow): EndedEntry | null {
  if (job.state !== "succeeded" && job.state !== "cancelled") return null
  const message = job.message ?? row.status
  return {
    id: endingId(job.id),
    at: Date.parse(job.finished_at ?? job.created_at) || Date.now(),
    notice: {
      // Stopped on request is news rather than a question.
      tone: job.state === "succeeded" ? "success" : "info",
      title: row.label,
      message,
      lines: linesBeyond(row.detail, message),
      action: null,
    },
  }
}

/** Ended within the day, so still worth showing after a reload. */
export function isRecent(job: JobPublic, now: number): boolean {
  const ended = Date.parse(job.finished_at ?? "")
  return Number.isFinite(ended) && now - ended <= RECENT_FOR
}

/**
 * The jobs seen running in this tab that have ended since, and what is running
 * now. An ending seen as it happens is one a person is told about on screen;
 * one found already over — after a reload, or in the listing's older pages —
 * is only recorded.
 */
export function endings(
  watched: ReadonlySet<string>,
  jobs: readonly JobPublic[]
): { watched: Set<string>; ended: JobPublic[] } {
  const running = new Set<string>()
  const ended: JobPublic[] = []
  for (const job of jobs) {
    if (isWorking(job)) running.add(job.id)
    else if (watched.has(job.id)) ended.push(job)
  }
  // Started a moment ago and not listed yet: still waited for.
  const listed = new Set(jobs.map((job) => job.id))
  for (const id of watched) if (!listed.has(id)) running.add(id)
  return { watched: running, ended }
}

/**
 * Whether an ending is told on screen: not a pipeline's run its schedule
 * started, which nobody was waiting for. Its failure still arrives, as
 * anything new in Needs you does.
 */
export function toldOnScreen(job: JobPublic): boolean {
  return pipelineRunOf(job)?.scheduled !== true
}

/**
 * What is new in Needs you since the page opened: not seen before, and about
 * something that happened after `since`. What was already waiting when the
 * page opened is in the sheet and the count; a card for it on every reload
 * would only repeat it.
 */
export function arrivals(
  known: ReadonlySet<string>,
  items: readonly AttentionItem[],
  since: number
): { known: Set<string>; arrived: AttentionItem[] } {
  const next = new Set(known)
  const arrived: AttentionItem[] = []
  for (const item of items) {
    if (next.has(item.id)) continue
    next.add(item.id)
    if (item.at >= since) arrived.push(item)
  }
  return { known: next, arrived }
}
