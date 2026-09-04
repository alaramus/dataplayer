import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { serverStorageKey } from "@/shared/servers/context"

export const TOKEN_KEY = "access_token"

/**
 * Client-side authentication state.
 *
 * Pinia holds only what the server does not. Everything else lives in
 * vue-query, so there are no hand-rolled caches with manual invalidation.
 */
export const useAuthStore = defineStore("auth", () => {
  const storageKey = serverStorageKey(TOKEN_KEY)
  const token = ref<string | null>(localStorage.getItem(storageKey))
  const isLoggedIn = computed(() => token.value !== null)

  function setToken(value: string) {
    token.value = value
    localStorage.setItem(storageKey, value)
  }

  function clear() {
    token.value = null
    localStorage.removeItem(storageKey)
  }

  /**
   * Take over whatever storage now says.
   *
   * The token is read once when the store is created, so another tab signing
   * out leaves this one holding a token that is gone from storage — and one
   * the server would still accept, so no request would ever reveal it.
   */
  function syncFromStorage() {
    token.value = localStorage.getItem(storageKey)
  }

  return { token, storageKey, isLoggedIn, setToken, clear, syncFromStorage }
})
