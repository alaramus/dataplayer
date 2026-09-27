import { computed } from "vue"
import type { ComputedRef, Ref } from "vue"

import type { JobPublic } from "@/client"
import { useAiAttention } from "@/features/ai/attention"
import { useHealthAttention } from "@/features/connectors/attention"
import { useRestartAttention } from "@/features/dashboards/attention"
import { useAccessAttention } from "@/features/shares/attention"
import { ranked } from "@/shared/notifications"
import type { AttentionItem } from "@/shared/notifications"
import { outstandingJobs } from "./attention"
import type { JobDescription } from "./attention"
import type { DismissedJobs } from "./dismissed"

/**
 * Which features have unfinished business worth showing (D115).
 *
 * The list, and the only place it is written down. A new kind of outstanding
 * thing is a composable in the feature that owns the subject and a line here;
 * the sheet is not touched, because it draws `AttentionItem`s and knows
 * nothing about what they are about.
 */

/** What a source may ask the screen to do, since none of them owns the layout. */
export interface AttentionHandlers {
  /** Show a connection's permissions page, where a request is answered (D61). */
  answerAccess: (connectorId: string) => void
  /** Show a connection's own window. */
  openConnection: (connectorId: string) => void
}

export function useAttention(
  handlers: AttentionHandlers,
  jobs: Ref<JobPublic[]>,
  describeJob: (job: JobPublic) => JobDescription,
  dismissed: DismissedJobs
): ComputedRef<AttentionItem[]> {
  const sources = [
    useAccessAttention(handlers.answerAccess),
    outstandingJobs(jobs, describeJob, dismissed.ids, dismissed.dismiss),
    useHealthAttention(handlers.openConnection),
    useRestartAttention(),
    useAiAttention(),
  ]
  return computed(() => ranked(sources.flatMap((source) => source.value)))
}
