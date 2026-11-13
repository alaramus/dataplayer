/**
 * The status line at the foot of a pipeline's canvas (D364): which thing it
 * says is the server's answer, and only the words are chosen here, so this is
 * tested without a screen.
 */

import type { PipelineStatus } from "@/client"
import { ageLabel } from "@/shared/freshness/freshness"
import { t } from "@/shared/i18n"

import { nextRunWords } from "./schedule"

/** What pressing the line's action does: open a link's choice, the schedule, or the history. */
export type StatusAction = "link" | "schedule" | "history"

export interface StatusLine {
  tone: "quiet" | "caution" | "working"
  text: string
  action: StatusAction | null
  actionLabel: string
  linkId: string | null
}

function since(iso: string | null | undefined, now: number): number | null {
  const at = Date.parse(iso ?? "")
  return Number.isNaN(at) ? null : Math.max(now - at, 0)
}

/** "2 links run continuously, 1 on the schedule", from the counts the server sent. */
export function runsWords(continuous: number, scheduled: number): string {
  const parts: string[] = []
  if (continuous > 0) parts.push(t("pipelines.status.continuous", { n: continuous }, continuous))
  if (scheduled > 0) parts.push(t("pipelines.status.scheduled", { n: scheduled }, scheduled))
  return parts.join(", ")
}

export function statusLine(status: PipelineStatus | undefined, now: number): StatusLine | null {
  if (status === undefined) return null
  const plain = { action: null, actionLabel: "", linkId: null }
  const continuous = status.continuous ?? 0
  const scheduled = status.scheduled ?? 0
  switch (status.kind) {
    case "empty":
      return { tone: "quiet", text: t("pipelines.status.empty"), ...plain }
    case "lacking":
      return {
        tone: "caution",
        text: t("pipelines.status.lacking", { needs: status.message ?? "" }),
        action: "link",
        actionLabel: t("pipelines.status.choose"),
        linkId: status.link_id ?? null,
      }
    case "no_schedule":
      return {
        tone: "caution",
        text: t("pipelines.status.no_schedule", { n: scheduled }, scheduled),
        action: "schedule",
        actionLabel: t("pipelines.status.set_schedule"),
        linkId: null,
      }
    case "retrying":
      return {
        tone: "caution",
        text: t("pipelines.status.retrying", { reason: status.message ?? "" }),
        action: "link",
        actionLabel: t("pipelines.status.open_link"),
        linkId: status.link_id ?? null,
      }
    case "ready":
      return { tone: "quiet", text: t("pipelines.status.ready", { runs: runsWords(continuous, scheduled) }), ...plain }
    case "on": {
      const parts = [t("pipelines.status.on", { age: ageLabel(since(status.since, now) ?? 0) })]
      const carried = since(status.last_at, now)
      if (continuous > 0) {
        parts.push(carried === null
          ? t("pipelines.status.nothing_yet")
          : t("pipelines.status.last_carried", { age: ageLabel(carried) }))
      }
      const next = scheduled > 0 ? nextRunWords(status.next_at, now) : null
      if (next !== null) parts.push(t("pipelines.status.next_run", { when: next }))
      return {
        tone: "working",
        text: parts.join(" · "),
        action: "history",
        actionLabel: t("pipelines.status.history"),
        linkId: null,
      }
    }
  }
}
