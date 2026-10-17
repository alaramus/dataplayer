/**
 * A pipeline's history as its window says it (D180): each run, and each time
 * the schedule came and started nothing. The rows and their order are the
 * server's; these only word them.
 */

import type { HistoryRun, PipelineHistory, PipelineRunPublic } from "@/client"
import { elapsed } from "@/features/queries/console"
import { t } from "@/shared/i18n"

import { clockOf, dayMonth } from "./schedule"

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
function ended(state: HistoryRun["state"]): string {
  return t(`pipelines.history.states.${state}`)
}

/** A moment in this browser's clock, with the year only when it is not this one: "26 Sep 03:00". */
export function momentWords(at: string, now: number): string {
  const moment = new Date(Date.parse(at))
  const thisYear = moment.getFullYear() === new Date(now).getFullYear()
  return `${dayMonth(moment, !thisYear)} ${clockOf(moment)}`
}

function took(run: HistoryRun, now: number): string | null {
  const started = Date.parse(run.started_at)
  if (run.state === "queued") return null
  if (run.state === "running") return t("pipelines.history.so_far", { time: elapsed(Math.max(0, now - started)) })
  const finished = Date.parse(run.finished_at ?? "")
  return Number.isNaN(finished) ? null : t("pipelines.history.took", { time: elapsed(Math.max(0, finished - started)) })
}

export function historyLine(row: HistoryRow, now: number): HistoryLine {
  if (row.kind !== "run") {
    return {
      key: `${row.kind}:${row.at}`,
      jobId: null,
      said: t(row.kind === "skipped" ? "pipelines.history.skipped" : "pipelines.history.missed", { reason: row.reason }),
      detail: `${momentWords(row.at, now)} · ${t("pipelines.history.by_schedule")}`,
      tone: "muted",
    }
  }
  const going = row.state === "queued" || row.state === "running"
  return {
    key: row.job_id,
    jobId: row.job_id,
    said: going ? ended(row.state) : row.message ?? ended(row.state),
    detail: [
      momentWords(row.started_at, now),
      t(row.scheduled ? "pipelines.history.by_schedule" : "pipelines.history.by_hand"),
      took(row, now),
    ].filter((part) => part !== null).join(" · "),
    tone: row.state === "failed" || row.state === "interrupted" ? "caution" : "plain",
  }
}

/** The strip over the canvas while an older run is shown: "Showing the run of 26 Sep 03:00". */
export function shownWords(run: PipelineRunPublic, now: number): string {
  return t("pipelines.history.showing", { when: momentWords(run.started_at, now) })
}
