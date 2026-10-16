import type { JobPublic } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { isWorking, progressOf } from "@/features/services/jobs"
import { contentsCounts, contentsMeasure } from "@/features/search/contents"
import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"
import { isActive } from "@/shared/operations"
import type { Operation } from "@/shared/operations"
import type { Tone } from "@/shared/ui"
import { pipelineBrief, pipelineLines, pipelineName, pipelineRunOf, settledSteps } from "./pipelineRuns"
import type { PipelineRunRecord } from "./pipelineRuns"
import { operationLines, settledCount, sourceOperationOf } from "./sourceOperations"
import {
  transferBrief, transferLines, transferMeasure, transferOf, transferStopHint,
} from "./transfers"
import type { TransferRecord } from "./transfers"

export interface ProcessRow {
  id: string
  source: "local" | "server"
  label: string
  /** What the footer says instead of the label, where that is shorter. */
  brief?: string
  detail: string
  status: string
  tone: Tone
  active: boolean
  paused: boolean
  progress: number | null
  measurement: string
  createdAt: number
  canPause: boolean
  canResume: boolean
  canStop: boolean
  controlsHint: string
}

const JOB_LABELS: Record<JobPublic["kind"], MessageKey> = {
  "service.create": "activity.jobs.service_create",
  "service.start": "activity.jobs.service_start",
  "service.stop": "activity.jobs.service_stop",
  "service.restart": "activity.jobs.service_restart",
  "service.delete": "activity.jobs.service_delete",
  "backup.create": "activity.jobs.backup_create",
  "backup.restore": "activity.jobs.backup_restore",
  "source.operation": "activity.jobs.source_operation",
  "metrics.store.create": "activity.jobs.metrics_store_create",
  "paste.transfer": "activity.jobs.paste_transfer",
  "pipeline.run": "activity.jobs.pipeline_run",
  "search.contents": "activity.jobs.search_contents",
}

/** What a kind of job is called. */
export function jobLabel(kind: JobPublic["kind"]): string {
  return t(JOB_LABELS[kind])
}

/**
 * What a job is called: a source operation by its action's title, a transfer
 * by its kind's, a pipeline's run by the pipeline, any other by its kind.
 */
export function jobTitle(job: JobPublic): string {
  const run = pipelineRunOf(job)
  if (run !== null) return t("activity.rows.pipeline_title", { name: run.pipelineName })
  return sourceOperationOf(job)?.title ?? transferOf(job)?.title ?? jobLabel(job.kind)
}

type State = JobPublic["state"] | Operation["state"]

function statusOf(state: State): string {
  return t(`activity.status.${state}`)
}

function toneOf(state: State): Tone {
  if (state === "succeeded") return "success"
  if (state === "failed") return "error"
  if (["cancelled", "interrupted", "paused"].includes(state)) return "warning"
  return "info"
}

export function localRow(item: Operation): ProcessRow {
  const active = isActive(item)
  const transferring = item.transfer !== null && item.transfer.loaded < item.transfer.total
  const batch = item.total > 1
  const measured = item.transfer
  const count = t("activity.rows.items_processed", { completed: item.completed, total: item.total })
  return {
    id: item.id, source: "local", label: item.label, detail: item.detail,
    status: statusOf(item.state), tone: toneOf(item.state), active,
    paused: item.state === "paused", createdAt: item.createdAt,
    progress: transferring && measured !== null ? measured.loaded / measured.total
      : item.state === "succeeded" ? 1 : batch ? item.completed / item.total : null,
    measurement: transferring && measured !== null
      ? `${t("activity.rows.sent", { loaded: formatSize(measured.loaded), total: formatSize(measured.total) })}${batch ? ` · ${count}` : ""}`
      : batch ? count : "",
    canPause: item.canPause, canResume: item.state === "paused" || item.state === "pausing",
    canStop: item.canStop,
    controlsHint: active ? batch
      ? t("activity.rows.batch_hint")
      : t("activity.rows.single_hint") : "",
  }
}

export function serverRow(job: JobPublic, subject: string | undefined): ProcessRow {
  const transfer = transferOf(job)
  if (transfer !== null) return transferRow(job, transfer)
  const run = pipelineRunOf(job)
  if (run !== null) return pipelineRow(job, run)
  const counts = contentsCounts(job)
  if (counts !== null) return contentsRow(job, contentsMeasure(counts))
  const active = isWorking(job)
  const operation = sourceOperationOf(job)
  const settled = operation === null ? 0 : settledCount(operation)
  const total = operation?.targets.length ?? 0
  return {
    id: job.id, source: "server",
    label: `${jobTitle(job)}${subject ? ` · ${subject}` : ` · ${job.id.slice(0, 8)}`}`,
    detail: [progressOf(job), ...(operation === null ? [] : operationLines(operation, active))].join("\n"),
    status: statusOf(job.state), tone: toneOf(job.state),
    active, paused: false,
    // A source operation counts the targets that have an outcome; anything
    // else has no measure and stays indeterminate.
    progress: job.state === "succeeded" ? 1 : active && operation !== null ? settled / total : null,
    measurement: operation === null ? "" : t("activity.rows.processed", { settled, total }),
    createdAt: Date.parse(job.created_at),
    canPause: false, canResume: false, canStop: active,
    controlsHint: !active ? "" : operation !== null
      ? t("activity.rows.operation_hint")
      : t("activity.rows.job_hint"),
  }
}

/**
 * A transfer between connections (D168): both connections in its name, the
 * item in hand, and bytes that were measured rather than estimated — a table
 * written as CSV has no total, so it has no bar either.
 */
function transferRow(job: JobPublic, transfer: TransferRecord): ProcessRow {
  const active = isWorking(job)
  const total = transfer.bytesTotal
  return {
    id: job.id, source: "server",
    label: `${transfer.title} · ${transfer.sourceLabel} → ${transfer.destinationLabel}`,
    brief: transferBrief(transfer),
    detail: transferLines(job, transfer).join("\n"),
    status: statusOf(job.state), tone: toneOf(job.state),
    active, paused: false,
    progress: job.state === "succeeded" ? 1
      : active && total !== null && total > 0 ? Math.min(transfer.bytesDone / total, 1) : null,
    measurement: transferMeasure(transfer),
    createdAt: Date.parse(job.created_at),
    canPause: false, canResume: false, canStop: active,
    controlsHint: active ? transferStopHint(transfer) : "",
  }
}

/**
 * A pipeline's run (D177): the pipeline by its name, the link in hand and how
 * many have ended; Stop ends the link running and the rest are not run.
 */
function pipelineRow(job: JobPublic, run: PipelineRunRecord): ProcessRow {
  const active = isWorking(job)
  const settled = settledSteps(run)
  const total = run.steps.length
  return {
    id: job.id, source: "server",
    label: t("activity.rows.pipeline_label", { name: pipelineName(run) }),
    brief: pipelineBrief(run),
    detail: pipelineLines(job, run).join("\n"),
    status: statusOf(job.state), tone: toneOf(job.state),
    active, paused: false,
    progress: job.state === "succeeded" ? 1 : active ? settled / total : null,
    measurement: t("activity.rows.links", { settled, total }),
    createdAt: Date.parse(job.created_at),
    canPause: false, canResume: false, canStop: active,
    controlsHint: active ? t("activity.rows.pipeline_hint") : "",
  }
}

/**
 * A search inside files (S7): counted by connections and matches, never named
 * by its words, which the row does not hold. Stop keeps what it found.
 */
function contentsRow(job: JobPublic, measurement: string): ProcessRow {
  const active = isWorking(job)
  return {
    id: job.id, source: "server",
    label: jobLabel(job.kind),
    detail: progressOf(job),
    status: statusOf(job.state), tone: toneOf(job.state),
    active, paused: false,
    progress: job.state === "succeeded" ? 1 : null,
    measurement,
    createdAt: Date.parse(job.created_at),
    canPause: false, canResume: false, canStop: active,
    controlsHint: active ? t("activity.rows.contents_hint") : "",
  }
}

/** Prefer work that is moving over a paused queue; never average unlike units. */
export function foreground(rows: ProcessRow[]): ProcessRow | undefined {
  return rows.find((row) => row.active && !row.paused) ?? rows.find((row) => row.active)
}
