import { defineStore } from "pinia"
import { computed, ref } from "vue"

const TOKEN_KEY = "access_token"

/**
 * Клиентское состояние аутентификации.
 *
 * В Pinia хранится только то, чего нет на сервере. Всё остальное живёт в
 * vue-query, чтобы не заводить самодельные кеши с ручной инвалидацией.
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
