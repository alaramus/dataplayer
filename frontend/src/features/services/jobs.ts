import { useQueryClient } from "@tanstack/vue-query"
import { onScopeDispose } from "vue"

import type { JobPublic } from "@/client"
import { connectorsKey } from "@/features/connectors/api"
import { jobsKey } from "@/features/operations/api"
import { backupsKey, servicesKey } from "@/features/services/api"
import { realtime } from "@/shared/realtime/client"

/**
 * What the server says about the work it is doing, and what to re-read for it.
 *
 * The socket carries a state and a step, and neither is stored here: an event
 * says "this changed", and the queries are what say what it changed to. That
 * is the same arrangement the run topic has, and the reason a message that
 * never arrives costs nothing — the job's own route is the authority.
 */
export const JOBS_TOPIC = "jobs"

/** One move of one job, as the server sends it. See app/jobs/topic.py. */
export interface JobEvent {
  job_id: string
  kind: string
  subject_id: string | null
  state: JobPublic["state"]
  step: string | null
  step_index: number
  step_count: number
  message: string | null
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled", "interrupted"])
const STATES = new Set(["queued", "running", ...TERMINAL])

export function isJobEvent(payload: unknown): payload is JobEvent {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "job_id" in payload && typeof payload.job_id === "string" &&
    "state" in payload && typeof payload.state === "string" && STATES.has(payload.state) &&
    "kind" in payload && typeof payload.kind === "string" &&
    "subject_id" in payload && (payload.subject_id === null || typeof payload.subject_id === "string") &&
    "step" in payload && (payload.step === null || typeof payload.step === "string") &&
    "step_index" in payload && typeof payload.step_index === "number" && Number.isInteger(payload.step_index) &&
    "step_count" in payload && typeof payload.step_count === "number" && Number.isInteger(payload.step_count) &&
    "message" in payload && (payload.message === null || typeof payload.message === "string")
  )
}

/**
 * Whether the connections have to be read again because of this event.
 *
 * A create that succeeded is a new connector; a delete that succeeded may have
 * left one behind that no longer works. Pure, so what a screen re-reads is a
 * rule with a test rather than a habit.
 */
export function touchesConnectors(event: JobEvent): boolean {
  return event.state === "succeeded" && event.kind.startsWith("service.")
}

/** Whether this event is about a database being copied out or written back. */
export function isBackupEvent(event: JobEvent): boolean {
  return event.kind.startsWith("backup.")
}

/**
 * Follow every job of this user for as long as the caller lives.
 *
 * Called once, from the workspace, exactly as the health topic is. Nothing is
 * stored: an event says something moved, and the queries say what it is now.
 */
export function useServiceJobs() {
  const queryClient = useQueryClient()
  const stop = realtime().subscribe(JOBS_TOPIC, (payload) => {
    if (!isJobEvent(payload)) return
    void queryClient.invalidateQueries({ queryKey: jobsKey })
    if (payload.kind.startsWith("service.")) {
      void queryClient.invalidateQueries({ queryKey: servicesKey })
    }
    if (payload.kind.startsWith("backup.")) {
      void queryClient.invalidateQueries({ queryKey: backupsKey })
    }
    if (touchesConnectors(payload)) {
      void queryClient.invalidateQueries({ queryKey: connectorsKey })
    }
  })
  onScopeDispose(stop)
  return { stop }
}

/**
 * How far a job has got, in the words the server chose.
 *
 * Never a percentage: nothing on this side knows how long a pull takes, and
 * the server deliberately does not say (D81).
 */
export function progressOf(job: {
  state: string
  step: string | null
  step_index: number
  step_count: number
  message: string | null
} | null | undefined): string {
  if (job === null || job === undefined) return ""
  if (TERMINAL.has(job.state)) return job.message ?? job.state
  if (job.step === null) return "Starting"
  return `${job.step} (${job.step_index} of ${job.step_count})`
}

export function isWorking(job: { state: string } | null | undefined): boolean {
  return job !== null && job !== undefined && !TERMINAL.has(job.state)
}
