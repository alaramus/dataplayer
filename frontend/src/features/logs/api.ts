import { useInfiniteQuery } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { LogsService } from "@/client"
import type { LogPage } from "@/client"

export type LevelChoice = "all" | "warning" | "error"
export type ProcessChoice = "all" | "backend" | "metrics" | "search-keeper"

export interface LogFilter {
  level: LevelChoice
  process: ProcessChoice
  text: string
}

/** How often a followed log is read again. */
export const FOLLOW_MS = 3000

export const logsKey = (filter: LogFilter) => ["logs", filter] as const

/**
 * The newest page first, then older ones on request, each starting before the
 * oldest entry already shown. Following reads them again on a timer.
 */
export function useLogs(
  filter: MaybeRefOrGetter<LogFilter>,
  options: { follow: MaybeRefOrGetter<boolean>; enabled: MaybeRefOrGetter<boolean> }
) {
  const current = computed(() => toValue(filter))
  return useInfiniteQuery({
    queryKey: computed(() => logsKey(current.value)),
    queryFn: async ({ pageParam }): Promise<LogPage> => (
      await LogsService.readLogs({
        query: {
          level: current.value.level,
          process: current.value.process,
          q: current.value.text.trim() || undefined,
          before: pageParam ?? undefined,
        },
      })
    ).data,
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.more ? last.entries.at(-1)?.time ?? null : null),
    refetchInterval: computed(() => (toValue(options.follow) ? FOLLOW_MS : false)),
    refetchOnWindowFocus: false,
    enabled: computed(() => toValue(options.enabled)),
  })
}
