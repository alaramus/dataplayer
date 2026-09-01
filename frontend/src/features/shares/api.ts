import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { SharesService } from "@/client"
import type { ShareCreate } from "@/client"

/**
 * The links made to one connection, and the making and taking back of them.
 *
 * Server state, so vue-query and not a store (D6). Keyed under the connection,
 * because that is what the dialog is open about.
 */

export const sharesKey = (connectorId: string) => ["shares", connectorId] as const

export function useShares(connectorId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(connectorId))
  return useQuery({
    queryKey: computed(() => sharesKey(id.value ?? "none")),
    queryFn: async () =>
      (
        await SharesService.listShares({
          query: { connector_id: id.value as string },
        })
      ).data,
    enabled: computed(() => id.value !== null),
  })
}

export function useCreateShare(connectorId: MaybeRefOrGetter<string | null>) {
  const queryClient = useQueryClient()
  const id = computed(() => toValue(connectorId))
  return useMutation({
    mutationFn: async (body: ShareCreate) =>
      (await SharesService.createShare({ body })).data,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: sharesKey(id.value ?? "none") }),
  })
}

export function useDeleteShare(connectorId: MaybeRefOrGetter<string | null>) {
  const queryClient = useQueryClient()
  const id = computed(() => toValue(connectorId))
  return useMutation({
    mutationFn: async (shareId: string) =>
      (await SharesService.deleteShare({ path: { share_id: shareId } })).data,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: sharesKey(id.value ?? "none") }),
  })
}
