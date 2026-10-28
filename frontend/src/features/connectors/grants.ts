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

/** The key an entry gets while there is no connection to read grants for. */
const NO_CONNECTION = "none"

export const directoryKey = ["users", "directory"] as const

export function useGrants(connectorId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(connectorId))
  return useQuery({
    queryKey: computed(() => grantsKey(id.value ?? NO_CONNECTION)),
    /**
     * Asked about the connection the entry was filed under, read back from its
     * key, and not about the one this call site holds now.
     *
     * Two places draw one connection's grants — the window's list and the
     * dialog opened over it — so they share a cache entry, and the entry
     * outlives whichever of them filed it, keeping that one's query function.
     * A function reading its own ref asked the server about the connection it
     * had once the dialog closed and left the list on screen with the row
     * still there: `/connectors/{connector_id}/grants`, answered 422.
     */
    queryFn: async ({ queryKey }) => {
      const connectorId = queryKey[1]
      if (typeof connectorId !== "string" || connectorId === NO_CONNECTION) {
        throw new Error("No connection to read grants for")
      }
      return (
        await ConnectorsService.readGrants({
          path: { connector_id: connectorId },
        })
      ).data
    },
    enabled: computed(() => typeof id.value === "string"),
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
      queryClient.invalidateQueries({
        queryKey: grantsKey(id.value ?? NO_CONNECTION),
      }),
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
      queryClient.invalidateQueries({
        queryKey: grantsKey(id.value ?? NO_CONNECTION),
      }),
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
