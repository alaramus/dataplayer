import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

import { TOKEN_KEY, useAuthStore } from "./auth"

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it("keeps the token so a reload finds it again", () => {
    const auth = useAuthStore()

    auth.setToken("a-token")

    expect(localStorage.getItem(TOKEN_KEY)).toBe("a-token")
    expect(auth.isLoggedIn).toBe(true)
  })

  it("forgets the token on sign out", () => {
    const auth = useAuthStore()
    auth.setToken("a-token")

    auth.clear()

    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(auth.isLoggedIn).toBe(false)
  })

  describe("syncFromStorage", () => {
    it("notices a sign out that happened in another tab", () => {
      const auth = useAuthStore()
      auth.setToken("a-token")
      localStorage.removeItem(TOKEN_KEY)

      auth.syncFromStorage()

      expect(auth.isLoggedIn).toBe(false)
    })

    it("adopts a token another tab signed in with", () => {
      const auth = useAuthStore()
      localStorage.setItem(TOKEN_KEY, "someone-elses-token")

      auth.syncFromStorage()

      expect(auth.token).toBe("someone-elses-token")
    })

    it("leaves an unchanged token alone", () => {
      const auth = useAuthStore()
      auth.setToken("a-token")

      auth.syncFromStorage()

      expect(auth.token).toBe("a-token")
    })
  })
})
