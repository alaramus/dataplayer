import { computed } from "vue"
import type { ComputedRef, Ref } from "vue"

import type { JobPublic } from "@/client"
import type { AttentionItem } from "@/shared/notifications"

/**
 * A job nobody was told about (D115).
 *
 * The rule lives here rather than in `features/services` because the jobs
 * listing is already read in this package, for the section that shows the ones
 * still running; asking for it twice would be two queries about one answer.
 */

/** Ended without doing what was asked, so somebody has to look. */
export function isOutstanding(job: JobPublic): boolean {
  return job.state === "failed" || job.state === "interrupted"
}

const WORDING: Record<"failed" | "interrupted", string> = {
  failed: "could not be completed",
  // What a restart leaves behind. Nothing replays it, and until now nothing
  // said so either (D81).
  interrupted: "stopped when the server restarted",
}

export function jobItem(
  job: JobPublic & { state: "failed" | "interrupted" },
  label: string,
  dismiss: () => void
): AttentionItem {
  return {
    id: `job:${job.id}`,
    tone: job.state === "failed" ? "error" : "warning",
    title: `${label} ${WORDING[job.state]}`,
    detail: job.message ?? `Last step: ${job.step ?? "none recorded"}`,
    at: Date.parse(job.finished_at ?? job.created_at ?? "") || Date.now(),
    action: null,
    dismiss,
  }
}

/**
 * The jobs worth a person's attention, minus the ones already waved away.
 *
 * Dismissal is by id and kept here: a failed job is news, and news that has
 * been read does not come back. The row itself is untouched — it is still in
 * the history the sheet lists below.
 */
export function outstandingJobs(
  jobs: Ref<JobPublic[]>,
  labelOf: (job: JobPublic) => string,
  waved: Ref<ReadonlySet<string>>,
  wave: (id: string) => void
): ComputedRef<AttentionItem[]> {
  return computed(() => jobs.value
    .filter(isOutstanding)
    .filter((job) => !waved.value.has(job.id))
    .map((job) => jobItem(
      job as JobPublic & { state: "failed" | "interrupted" },
      labelOf(job),
      () => { wave(job.id) }
    )))
}
