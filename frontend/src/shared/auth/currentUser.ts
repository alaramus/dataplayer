import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"

import { UsersService } from "@/client"
import { useAuthStore } from "@/stores/auth"

export const currentUserKey = ["users", "me"] as const

/**
 * The current account is shared by the application header and feature pages.
 * Keep it in the query cache, which is cleared on sign-out, rather than
 * duplicating server state in the auth store.
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
