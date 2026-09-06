import { computed, ref } from "vue"
import type { ComputedRef, Ref } from "vue"

import type { JobPublic } from "@/client"
import { useHealthAttention } from "@/features/connectors/attention"
import { useAccessAttention } from "@/features/shares/attention"
import { ranked } from "@/shared/notifications"
import type { AttentionItem } from "@/shared/notifications"
import { outstandingJobs } from "./attention"

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
  jobLabel: (job: JobPublic) => string
): ComputedRef<AttentionItem[]> {
  const waved = ref(new Set<string>())
  const sources = [
    useAccessAttention(handlers.answerAccess),
    outstandingJobs(jobs, jobLabel, waved, (id) => {
      waved.value = new Set([...waved.value, id])
    }),
    useHealthAttention(handlers.openConnection),
  ]
  return computed(() => ranked(sources.flatMap((source) => source.value)))
}
