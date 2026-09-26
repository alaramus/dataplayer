import type { JobPublic } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { isWorking, progressOf } from "@/features/services/jobs"
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

export const JOB_LABELS: Record<JobPublic["kind"], string> = {
  "service.create": "Start service",
  "service.start": "Start service",
  "service.stop": "Stop service",
  "service.restart": "Restart service",
  "service.delete": "Delete service",
  "backup.create": "Create backup",
  "backup.restore": "Restore backup",
  "source.operation": "Source operation",
  "metrics.store.create": "Start metrics store",
  "paste.transfer": "Transfer",
  "pipeline.run": "Pipeline run",
}

/**
 * What a job is called: a source operation by its action's title, a transfer
 * by its kind's, a pipeline's run by the pipeline, any other by its kind.
 */
export function jobTitle(job: JobPublic): string {
  const run = pipelineRunOf(job)
  if (run !== null) return `Pipeline ${run.pipelineName}`
  return sourceOperationOf(job)?.title ?? transferOf(job)?.title ?? JOB_LABELS[job.kind]
}

const STATUS: Record<JobPublic["state"] | Operation["state"], string> = {
  queued: "Queued", running: "Running", pausing: "Pausing after current",
  paused: "Paused", stopping: "Stopping after current", succeeded: "Completed",
  failed: "Failed", cancelled: "Stopped", interrupted: "Interrupted",
}

function toneOf(state: JobPublic["state"] | Operation["state"]): Tone {
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
  const count = `${item.completed} of ${item.total} items processed`
  return {
    id: item.id, source: "local", label: item.label, detail: item.detail,
    status: STATUS[item.state], tone: toneOf(item.state), active,
    paused: item.state === "paused", createdAt: item.createdAt,
    progress: transferring && measured !== null ? measured.loaded / measured.total
      : item.state === "succeeded" ? 1 : batch ? item.completed / item.total : null,
    measurement: transferring && measured !== null
      ? `${formatSize(measured.loaded)} / ${formatSize(measured.total)} sent${batch ? ` · ${count}` : ""}`
      : batch ? count : "",
    canPause: item.canPause, canResume: item.state === "paused" || item.state === "pausing",
    canStop: item.canStop,
    controlsHint: active ? batch
      ? "Pause and stop take effect after the current item. Completed changes are kept."
      : "This operation cannot be paused or stopped. Closing this window leaves it running." : "",
  }
}

export function serverRow(job: JobPublic, subject: string | undefined): ProcessRow {
  const transfer = transferOf(job)
  if (transfer !== null) return transferRow(job, transfer)
  const run = pipelineRunOf(job)
  if (run !== null) return pipelineRow(job, run)
  const active = isWorking(job)
  const operation = sourceOperationOf(job)
  const settled = operation === null ? 0 : settledCount(operation)
  const total = operation?.targets.length ?? 0
  return {
    id: job.id, source: "server",
    label: `${jobTitle(job)}${subject ? ` · ${subject}` : ` · ${job.id.slice(0, 8)}`}`,
    detail: [progressOf(job), ...(operation === null ? [] : operationLines(operation, active))].join("\n"),
    status: STATUS[job.state], tone: toneOf(job.state),
    active, paused: false,
    // A source operation counts the targets that have an outcome; anything
    // else has no measure and stays indeterminate.
    progress: job.state === "succeeded" ? 1 : active && operation !== null ? settled / total : null,
    measurement: operation === null ? "" : `${String(settled)} of ${String(total)} processed`,
    createdAt: Date.parse(job.created_at),
    canPause: false, canResume: false, canStop: active,
    controlsHint: !active ? "" : operation !== null
      ? "Cancelling stops before the next target; what is already done stays done."
      : "Cancellation keeps completed changes. This job does not support pause.",
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
    status: STATUS[job.state], tone: toneOf(job.state),
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
    label: `Pipeline · ${pipelineName(run)}`,
    brief: pipelineBrief(run),
    detail: pipelineLines(job, run).join("\n"),
    status: STATUS[job.state], tone: toneOf(job.state),
    active, paused: false,
    progress: job.state === "succeeded" ? 1 : active ? settled / total : null,
    measurement: `${String(settled)} of ${String(total)} links`,
    createdAt: Date.parse(job.created_at),
    canPause: false, canResume: false, canStop: active,
    controlsHint: active ? "Stops the link running now; the links after it are not run." : "",
  }
}

/** Prefer work that is moving over a paused queue; never average unlike units. */
export function foreground(rows: ProcessRow[]): ProcessRow | undefined {
  return rows.find((row) => row.active && !row.paused) ?? rows.find((row) => row.active)
}
