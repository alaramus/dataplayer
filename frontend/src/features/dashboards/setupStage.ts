/**
 * What the dashboards card says about the store, from the status the server
 * gave. One of four stages; `ready` never reaches this.
 */

import type { StoreStatus } from "@/client"
import { t } from "@/shared/i18n"

export type SetupStage =
  | { kind: "offer"; canStart: boolean; startReason: string | null }
  | { kind: "wait" }
  | { kind: "starting"; step: string; progress: number | null }
  | { kind: "trouble"; message: string; canStart: boolean; canRemove: boolean }

export function setupStage(status: StoreStatus): SetupStage {
  const canStart = status.may_set_up && status.start?.available === true
  if (status.state === "starting") {
    const job = status.job
    const count = job?.step_count ?? 0
    return {
      kind: "starting",
      step: job?.step ? t("dashboards.setup.now", { step: job.step }) : t("dashboards.setup.waiting"),
      progress: count > 0 ? (job?.step_index ?? 0) / count : null,
    }
  }
  if (status.state === "failed") {
    return {
      kind: "trouble",
      message: t("dashboards.setup.start_failed_message", {
        message: status.message ?? t("dashboards.setup.job_failed"),
      }),
      canStart,
      canRemove: false,
    }
  }
  if (status.state === "unreachable") {
    return {
      kind: "trouble",
      message: status.message ?? t("dashboards.setup.not_answering"),
      canStart: false,
      // A store gone for good is taken away the way a working one is.
      canRemove: status.may_set_up,
    }
  }
  if (!status.may_set_up) return { kind: "wait" }
  return {
    kind: "offer",
    canStart,
    startReason: canStart ? null : (status.start?.reason ?? t("dashboards.setup.cannot_start")),
  }
}
