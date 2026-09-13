/**
 * What the dashboards card says about the store, from the status the server
 * gave. One of four stages; `ready` never reaches this.
 */

import type { StoreStatus } from "@/client"

export type SetupStage =
  | { kind: "offer"; canStart: boolean; startReason: string | null }
  | { kind: "wait" }
  | { kind: "starting"; step: string; progress: number | null }
  | { kind: "trouble"; message: string; canStart: boolean }

export function setupStage(status: StoreStatus): SetupStage {
  const canStart = status.may_set_up && status.start?.available === true
  if (status.state === "starting") {
    const job = status.job
    const count = job?.step_count ?? 0
    return {
      kind: "starting",
      step: job?.step ? `Now ${job.step}` : "Waiting to begin",
      progress: count > 0 ? (job?.step_index ?? 0) / count : null,
    }
  }
  if (status.state === "failed") {
    return {
      kind: "trouble",
      message: `The metrics store could not be started: ${status.message ?? "the job failed"}`,
      canStart,
    }
  }
  if (status.state === "unreachable") {
    return {
      kind: "trouble",
      message: status.message ?? "The metrics store is not answering",
      canStart: false,
    }
  }
  if (!status.may_set_up) return { kind: "wait" }
  return {
    kind: "offer",
    canStart,
    startReason: canStart ? null : (status.start?.reason ?? "Services cannot be started here"),
  }
}
