import { useInfiniteQuery } from "@tanstack/vue-query"

import { JobsService } from "@/client"

export const jobsKey = ["jobs"] as const
const PAGE_SIZE = 50

export function useJobs() {
  return useInfiniteQuery({
    queryKey: jobsKey,
    initialPageParam: 0,
    queryFn: async ({ pageParam, signal }) => (await JobsService.readJobs({
      query: { skip: pageParam, limit: PAGE_SIZE }, signal,
    })).data,
    getNextPageParam: (last, pages) => {
      const read = pages.reduce((total, page) => total + page.data.length, 0)
      return read < last.count ? read : undefined
    },
    refetchInterval: (query) => (query.state.data?.pages[0]?.active_count ?? 0) > 0 ? 3000 : 15000,
    refetchIntervalInBackground: true,
  })
}
