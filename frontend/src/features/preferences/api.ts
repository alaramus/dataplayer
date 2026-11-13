import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"

import { AiService, UsersService } from "@/client"
import type { McpTokenCreate, PreferencesPublic, PreferencesUpdate } from "@/client"

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

/** How full the person's own storage is, against its limit (D324). */
export function useMyStorage() {
  return useQuery({
    queryKey: ["storage", "me"] as const,
    queryFn: async () => (await UsersService.readMyStorage()).data,
  })
}

/** The person's MCP access tokens (D358); the token itself is never listed. */
export const mcpTokensKey = ["ai", "mcp-tokens"] as const

export function useMcpTokens() {
  return useQuery({
    queryKey: mcpTokensKey,
    queryFn: async () => (await AiService.readMcpTokens()).data,
  })
}

function useTokenMutation<T, R>(run: (input: T) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: mcpTokensKey })
    },
  })
}

/** Its answer is the one place the token itself is seen. */
export function useCreateMcpToken() {
  return useTokenMutation(
    async (body: McpTokenCreate) => (await AiService.createMcpToken({ body })).data
  )
}

export function useDeleteMcpToken() {
  return useTokenMutation(
    async (tokenId: string) => (await AiService.deleteMcpToken({ path: { token_id: tokenId } })).data
  )
}
