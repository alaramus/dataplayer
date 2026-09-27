/**
 * A pipeline's history as its window says it (D180): each run, and each time
 * the schedule came and started nothing. The rows and their order are the
 * server's; these only word them.
 */

import type { HistoryRun, PipelineHistory, PipelineRunPublic } from "@/client"
import { elapsed } from "@/features/queries/console"

import { TIME } from "./schedule"

export type HistoryRow = PipelineHistory["rows"][number]

export interface HistoryLine {
  key: string
  /** The run it shows on the canvas when pressed; a skip or a miss shows none. */
  jobId: string | null
  said: string
  /** When, who started it and how long it took: "26 Sep 03:00 · by the schedule · took 12.4 s". */
  detail: string
  tone: "plain" | "caution" | "muted"
}

/** What a run that ended with no sentence of its own says instead. */
const ENDED: Record<HistoryRun["state"], string> = {
  queued: "Waiting to start",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
  cancelled: "Stopped",
  interrupted: "Interrupted",
}

// Named here rather than by the locale: ICU versions shorten September as
// "Sep" or as "Sept", so one browser would name a run differently from another.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const

/** A moment in this browser's clock, with the year only when it is not this one: "26 Sep 03:00". */
export function momentWords(at: string, now: number): string {
  const moment = new Date(Date.parse(at))
  const year = moment.getFullYear() === new Date(now).getFullYear() ? "" : ` ${String(moment.getFullYear())}`
  const day = `${String(moment.getDate())} ${MONTHS[moment.getMonth()] ?? ""}${year}`
  return `${day} ${moment.toLocaleTimeString("en-GB", TIME)}`
}

function took(run: HistoryRun, now: number): string | null {
  const started = Date.parse(run.started_at)
  if (run.state === "queued") return null
  if (run.state === "running") return `${elapsed(Math.max(0, now - started))} so far`
  const finished = Date.parse(run.finished_at ?? "")
  return Number.isNaN(finished) ? null : `took ${elapsed(Math.max(0, finished - started))}`
}

export function historyLine(row: HistoryRow, now: number): HistoryLine {
  if (row.kind !== "run") {
    return {
      key: `${row.kind}:${row.at}`,
      jobId: null,
      said: `${row.kind === "skipped" ? "Skipped" : "Missed"}: ${row.reason}`,
      detail: `${momentWords(row.at, now)} · by the schedule`,
      tone: "muted",
    }
  }
  const going = row.state === "queued" || row.state === "running"
  return {
    key: row.job_id,
    jobId: row.job_id,
    said: going ? ENDED[row.state] : row.message ?? ENDED[row.state],
    detail: [
      momentWords(row.started_at, now),
      row.scheduled ? "by the schedule" : "by hand",
      took(row, now),
    ].filter((part) => part !== null).join(" · "),
    tone: row.state === "failed" || row.state === "interrupted" ? "caution" : "plain",
  }
}

/** The strip over the canvas while an older run is shown: "Showing the run of 26 Sep 03:00". */
export function shownWords(run: PipelineRunPublic, now: number): string {
  return `Showing the run of ${momentWords(run.started_at, now)}`
}
