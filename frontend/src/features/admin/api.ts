import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"

import { UsersService } from "@/client"
import type { UserInvite, UserUpdate } from "@/client"

/**
 * The accounts an administrator manages.
 *
 * Separate from the directory in `features/connectors/grants.ts`, which any
 * signed-in user reads to name a colleague. These routes are the superuser's
 * and answer 403 to anybody else — an administrator has rights over accounts
 * and none over data (D34), and this is the whole of the first half.
 */
export const usersKey = ["users", "all"] as const

export function useUsers() {
  return useQuery({
    queryKey: usersKey,
    queryFn: async () => (await UsersService.readUsers({ query: { limit: 1000 } })).data,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: UserInvite) =>
      (await UsersService.createUser({ body })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  })
}

/** A new link to choose a password; the previous one, and any password, stop working. */
export function useInviteUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (userId: string) =>
      (await UsersService.inviteUser({ path: { user_id: userId } })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { userId: string; body: UserUpdate }) =>
      (
        await UsersService.updateUser({
          path: { user_id: payload.userId },
          body: payload.body,
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  })
}

export function useDeleteUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (userId: string) =>
      (await UsersService.deleteUser({ path: { user_id: userId } })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  })
}
