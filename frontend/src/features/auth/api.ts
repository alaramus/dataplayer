import { useMutation } from "@tanstack/vue-query"

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
