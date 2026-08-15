import { MutationCache, QueryCache, QueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"

import { client } from "@/client/client.gen"
import { router } from "@/router"
import { useAuthStore } from "@/stores/auth"

export function configureApiClient() {
  client.setConfig({
    baseURL: import.meta.env.VITE_API_URL ?? "",
    // The client applies the Bearer scheme itself, per the OpenAPI security.
    auth: () => useAuthStore().token ?? "",
  })
}

function handleApiError(error: Error) {
  if (error instanceof AxiosError && [401, 403].includes(error.response?.status ?? 0)) {
    useAuthStore().clear()
    void router.push({ name: "login" })
  }
}

export function createQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleApiError }),
    mutationCache: new MutationCache({ onError: handleApiError }),
  })
}
