import type { JobPublic } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { isWorking, progressOf } from "@/features/services/jobs"
import { isActive } from "@/shared/operations"
import type { Operation } from "@/shared/operations"
import type { Tone } from "@/shared/ui"
import { operationLines, settledCount, sourceOperationOf } from "./sourceOperations"

export interface ProcessRow {
  id: string
  source: "local" | "server"
  label: string
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
}

/** What a job is called: a source operation by its action's title, any other by its kind. */
export function jobTitle(job: JobPublic): string {
  return sourceOperationOf(job)?.title ?? JOB_LABELS[job.kind]
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

/** Prefer work that is moving over a paused queue; never average unlike units. */
export function foreground(rows: ProcessRow[]): ProcessRow | undefined {
  return rows.find((row) => row.active && !row.paused) ?? rows.find((row) => row.active)
}
