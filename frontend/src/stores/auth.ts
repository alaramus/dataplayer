import { defineStore } from "pinia"
import { computed, ref } from "vue"

const TOKEN_KEY = "access_token"

/**
 * Client-side authentication state.
 *
 * Pinia holds only what the server does not. Everything else lives in
 * vue-query, so there are no hand-rolled caches with manual invalidation.
 */
export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const isLoggedIn = computed(() => token.value !== null)

  function setToken(value: string) {
    token.value = value
    localStorage.setItem(TOKEN_KEY, value)
  }

  function clear() {
    token.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  return { token, isLoggedIn, setToken, clear }
})
