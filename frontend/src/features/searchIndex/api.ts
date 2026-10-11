import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import type { Ref } from "vue"
import { computed } from "vue"

import { SearchService } from "@/client"
import type { KeepState, KeepUpdate } from "@/client"
import { isBusy } from "@/features/searchIndex/state"

/**
 * Kept lists of names, as server state (D212). The worker that reads them is
 * another process and says nothing on the socket (D214), so a screen showing
 * one asks again: often while something is about to change, rarely otherwise.
 */
export const keptKey = ["search-kept"] as const

export function keepKey(connectorId: string) {
  return [...keptKey, connectorId] as const
}

const BUSY_MS = 2000
const IDLE_MS = 30_000

export function useKeptLists() {
  return useQuery({
    queryKey: keptKey,
    queryFn: async () => (await SearchService.readKept()).data,
    refetchInterval: (query) =>
      query.state.data?.lists.some(isBusy) === true ? BUSY_MS : IDLE_MS,
  })
}

export function useKeepState(connectorId: Ref<string | null>) {
  return useQuery({
    queryKey: computed(() => keepKey(connectorId.value ?? "")),
    queryFn: async () =>
      (await SearchService.readKeep({ path: { connector_id: connectorId.value ?? "" } })).data,
    enabled: computed(() => connectorId.value !== null),
    refetchInterval: (query) =>
      query.state.data !== undefined && isBusy(query.state.data) ? BUSY_MS : IDLE_MS,
  })
}

function useSettled() {
  const queryClient = useQueryClient()
  return async (state: KeepState) => {
    queryClient.setQueryData(keepKey(state.connector_id), state)
    await queryClient.invalidateQueries({ queryKey: keptKey })
  }
}

export function useChangeKeep() {
  const settled = useSettled()
  return useMutation({
    mutationFn: async ({ connectorId, body }: { connectorId: string; body: KeepUpdate }) =>
      (await SearchService.changeKeep({ path: { connector_id: connectorId }, body })).data,
    onSuccess: settled,
  })
}

export function useRefreshKeep() {
  const settled = useSettled()
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (await SearchService.refreshKeep({ path: { connector_id: connectorId } })).data,
    onSuccess: settled,
  })
}

export function useAddContents() {
  const settled = useSettled()
  return useMutation({
    mutationFn: async ({ connectorId, nodeId }: { connectorId: string; nodeId: string | null }) =>
      (
        await SearchService.addContents({
          path: { connector_id: connectorId },
          body: { node_id: nodeId },
        })
      ).data,
    onSuccess: settled,
  })
}

export function useRemoveContents() {
  const settled = useSettled()
  return useMutation({
    mutationFn: async ({ connectorId, nodeId }: { connectorId: string; nodeId: string }) =>
      (
        await SearchService.removeContents({
          path: { connector_id: connectorId },
          query: { node_id: nodeId },
        })
      ).data,
    onSuccess: settled,
  })
}
