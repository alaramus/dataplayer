import type { QueryClient } from "@tanstack/vue-query"

import { router } from "@/router"
import { useAuthStore } from "@/stores/auth"
import { closeRealtime } from "@/shared/realtime/client"

/**
 * Keep tabs connected to the same server on the same session.
 *
 * A 401 already sends the user to the login page, but signing out elsewhere
 * produces no 401 at all: the token stays valid on the server until it
 * expires, so this tab would keep working with a session the user believes
 * they ended. The browser reports the change through the `storage` event,
 * which fires only in the tabs that did not make it.
 */
export function watchSessionAcrossTabs(queryClient: QueryClient) {
  const auth = useAuthStore()
  window.addEventListener("storage", (event) => {
    // A null key means the whole storage was cleared rather than one entry.
    if (event.key !== null && event.key !== auth.storageKey) return

    if (localStorage.getItem(auth.storageKey) === auth.token) return

    auth.syncFromStorage()
    closeRealtime()
    // Whoever is here now is not who the cached answers belong to.
    queryClient.clear()
    if (!auth.isLoggedIn) {
      void router.push({ name: "login" })
    }
  })
}
