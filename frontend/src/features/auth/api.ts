import { useMutation, useQuery } from "@tanstack/vue-query"
import { computed } from "vue"

import { LoginService, UsersService } from "@/client"
import { useAuthStore } from "@/stores/auth"

export interface Credentials {
  username: string
  password: string
}

export function useLogin() {
  const auth = useAuthStore()

  return useMutation({
    mutationFn: async (credentials: Credentials) => {
      const response = await LoginService.loginAccessToken({ body: credentials })
      return response.data
    },
    onSuccess: (data) => {
      auth.setToken(data.access_token)
    },
  })
}

export const currentUserKey = ["users", "me"] as const

/**
 * Who is signed in.
 *
 * Server state, so vue-query and not the auth store: the store holds the
 * token, which is the one thing the server does not send. Asked once and kept,
 * because nothing in a session changes who is holding it — the cache is
 * cleared on sign-out along with everything else.
 */
export function useCurrentUser() {
  const auth = useAuthStore()
  return useQuery({
    queryKey: currentUserKey,
    queryFn: async () => (await UsersService.readUserMe()).data,
    enabled: computed(() => auth.isLoggedIn),
    staleTime: Number.POSITIVE_INFINITY,
  })
}
