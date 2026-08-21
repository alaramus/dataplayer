import { MutationCache, QueryCache, QueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"

import { client } from "@/client/client.gen"
import { router } from "@/router"
import { useAuthStore } from "@/stores/auth"

// Retries for everything else stay at the vue-query default.
const RETRIES = 3

export function configureApiClient() {
  client.setConfig({
    baseURL: import.meta.env.VITE_API_URL ?? "",
    // The client applies the Bearer scheme itself, per the OpenAPI security.
    auth: () => useAuthStore().token ?? "",
  })
}

/** The server refusing who we are, as opposed to a request going wrong. */
function isAuthFailure(error: Error): boolean {
  return (
    error instanceof AxiosError && [401, 403].includes(error.response?.status ?? 0)
  )
}

function handleApiError(error: Error) {
  if (isAuthFailure(error)) {
    useAuthStore().clear()
    void router.push({ name: "login" })
  }
}

export function createQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleApiError }),
    mutationCache: new MutationCache({ onError: handleApiError }),
    defaultOptions: {
      queries: {
        // A rejected token will be rejected again. Retrying it only leaves a
        // half-working page on screen for several seconds before the user is
        // sent to the login page.
        retry: (failureCount, error) => !isAuthFailure(error) && failureCount < RETRIES,
      },
    },
  })
}
