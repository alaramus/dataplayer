import { useMutation, useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { LoginService } from "@/client"
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

/** Whom a link to choose a password is for; refused once it no longer works. */
export function useInvitationHolder(token: Ref<string>) {
  return useQuery({
    queryKey: computed(() => ["invitation", token.value]),
    enabled: computed(() => token.value !== ""),
    retry: false,
    queryFn: async () =>
      (await LoginService.invitationHolder({ body: { token: token.value } })).data,
  })
}

export function useAcceptInvitation() {
  return useMutation({
    mutationFn: async (body: { token: string; new_password: string }) =>
      (await LoginService.acceptInvitation({ body })).data,
  })
}
