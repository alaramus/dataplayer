import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"

import { UsersService } from "@/client"
import type { PreferencesPublic, PreferencesUpdate } from "@/client"

/**
 * What this user chose for themselves. Server state, so vue-query and not
 * Pinia (D6): the answer follows the account rather than the browser, and the
 * one thing reading it apart from the screen — the dots — must see a change
 * made in another tab the moment the query says so.
 */
export const preferencesKey = ["preferences", "me"] as const

export function usePreferences() {
  return useQuery({
    queryKey: preferencesKey,
    queryFn: async () => (await UsersService.readMyPreferences()).data,
    // Rarely changed and cheap to hold: re-reading it on every screen that
    // asks would be a request per tab per focus for one word.
    staleTime: 300_000,
  })
}

export function useUpdatePreferences() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: PreferencesUpdate) =>
      (await UsersService.updateMyPreferences({ body })).data,
    // The answer is the whole of what was stored, so it is put in place of
    // what was cached rather than invalidated and read again.
    onSuccess: (saved: PreferencesPublic) => {
      queryClient.setQueryData(preferencesKey, saved)
    },
  })
}
