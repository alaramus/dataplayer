import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import type { Ref } from "vue"
import { computed } from "vue"

import { CopiesService } from "@/client"

/** A person's copy history, as server state (D460). */
export const copiesKey = ["copies"] as const

export function useCopies(query: Ref<string>, enabled: Ref<boolean>) {
  return useQuery({
    queryKey: computed(() => [...copiesKey, query.value.trim()] as const),
    queryFn: async () => {
      const q = query.value.trim()
      return (await CopiesService.readCopies({ query: q === "" ? {} : { q } })).data
    },
    enabled,
    placeholderData: (previous) => previous,
  })
}

/** One copy's whole text: the list carries only its start. */
export async function wholeText(copyId: string): Promise<string> {
  return (await CopiesService.readCopy({ path: { copy_id: copyId } })).data.text
}

export function useDeleteCopies() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (ids: string[] | null) =>
      ids === null
        ? (await CopiesService.clearCopies()).data
        : (await CopiesService.deleteCopies({ body: { ids } })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: copiesKey }),
  })
}
