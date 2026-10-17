import { MutationCache, QueryCache, QueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"

import { client } from "@/client/client.gen"
import { router } from "@/router"
import { shouldRetry } from "@/shared/api/retry"
import { currentLanguage } from "@/shared/i18n"
import { useAuthStore } from "@/stores/auth"
import { serverContext } from "@/shared/servers/context"

// How many times a failure that might pass is asked about again. The vue-query
// default; what changed is which failures are asked about at all.
const RETRIES = 3

export function configureApiClient() {
  client.setConfig({
    baseURL: serverContext().active.url,
    // The client applies the Bearer scheme itself, per the OpenAPI security.
    auth: () => useAuthStore().token ?? "",
  })
  // What a source writes is worded on the server, in the language asked for
  // (D226) — the interface's, not the browser's.
  client.instance.interceptors.request.use((config) => {
    config.headers.set("Accept-Language", currentLanguage())
    return config
  })
}

/**
 * The server refusing who we are, as opposed to refusing what we asked.
 *
 * 401 only. 403 used to be on this list, back when it was what an unusable
 * token got; it now means the caller is known and this is not theirs — too low
 * a level on a connection, or an administrator's route. Signing somebody out
 * for that would end the session over a button they should not have been
 * offered. See D33.
 */
function isAuthFailure(error: Error): boolean {
  return error instanceof AxiosError && error.response?.status === 401
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
        // sent to the login page — and the same is true of every other
        // refusal the server made on the merits, which is what `shouldRetry`
        // is about.
        retry: (failureCount, error) =>
          !isAuthFailure(error) && shouldRetry(failureCount, error, RETRIES),
      },
    },
  })
}
