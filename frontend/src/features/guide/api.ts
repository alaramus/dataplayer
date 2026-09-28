import { useQuery } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { GuideService } from "@/client"

/** The guide changes with a release and nowhere else, so nothing refetches it. */
export const guidePagesKey = ["guide", "pages"] as const
export const guidePageKey = (key: string) => ["guide", "page", key] as const

export function useGuidePages() {
  return useQuery({
    queryKey: guidePagesKey,
    queryFn: async () => (await GuideService.readGuidePages()).data,
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useGuidePage(key: MaybeRefOrGetter<string>) {
  const current = computed(() => toValue(key))
  return useQuery({
    queryKey: computed(() => guidePageKey(current.value)),
    queryFn: async () => (
      await GuideService.readGuidePage({ path: { key: current.value } })
    ).data,
    staleTime: Number.POSITIVE_INFINITY,
  })
}
