import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { ConnectorsService, UsersService } from "@/client"
import type { GrantWrite, UserBrief } from "@/client"

/**
 * Who else may reach a connection, and everybody it could be offered to.
 *
 * Server state, so vue-query and not a store. The list of grants is keyed
 * under the connection it belongs to: two share dialogs open at once are two
 * connections, and one cache entry each.
 */
export const grantsKey = (connectorId: string) =>
  ["connectors", connectorId, "grants"] as const

export const directoryKey = ["users", "directory"] as const

export function useGrants(connectorId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(connectorId))
  return useQuery({
    queryKey: computed(() => grantsKey(id.value ?? "none")),
    queryFn: async () =>
      (
        await ConnectorsService.readGrants({
          path: { connector_id: id.value as string },
        })
      ).data,
    enabled: computed(() => id.value !== null),
  })
}

export function useDirectory(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: directoryKey,
    queryFn: async () => (await UsersService.readDirectory()).data,
    enabled: computed(() => toValue(enabled)),
  })
}

export function useWriteGrant(connectorId: MaybeRefOrGetter<string | null>) {
  const queryClient = useQueryClient()
  const id = computed(() => toValue(connectorId))
  return useMutation({
    mutationFn: async (body: GrantWrite) =>
      (
        await ConnectorsService.writeGrant({
          path: { connector_id: id.value as string },
          body,
        })
      ).data,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: grantsKey(id.value ?? "none") }),
  })
}

export function useRevokeGrant(connectorId: MaybeRefOrGetter<string | null>) {
  const queryClient = useQueryClient()
  const id = computed(() => toValue(connectorId))
  return useMutation({
    mutationFn: async (userId: string) =>
      (
        await ConnectorsService.revokeGrant({
          path: { connector_id: id.value as string, user_id: userId },
        })
      ).data,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: grantsKey(id.value ?? "none") }),
  })
}

/**
 * Whom this connection can still be offered to.
 *
 * A pure function so it can be tested without mounting the dialog. Everybody
 * who already holds a grant is left out: their level is changed on their own
 * row, and offering them again in the picker would be a second way to do the
 * same thing that could disagree with the first.
 */
export function offerable(
  directory: readonly UserBrief[],
  held: readonly { user_id: string }[]
): UserBrief[] {
  const taken = new Set(held.map((grant) => grant.user_id))
  return directory.filter((user) => !taken.has(user.id))
}
