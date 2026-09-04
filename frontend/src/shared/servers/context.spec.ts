import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ACTIVE_SERVER_KEY, LEGACY_SERVER_KEY, PROFILES_KEY, scopedServerKey } from "./profiles"

const alpha = { name: "Alpha", url: "https://alpha.example/player" }
const beta = { name: "Beta", url: "https://beta.example" }

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState({}, "", "/")
  vi.stubEnv("VITE_API_URL", alpha.url)
  vi.resetModules()
  setActivePinia(createPinia())
})
afterEach(() => { vi.unstubAllEnvs(); window.history.replaceState({}, "", "/") })

describe("one server context per document", () => {
  it("adopts legacy data once and never gives it to a changed build default", async () => {
    localStorage.setItem("access_token", "alpha-token")
    const original = await import("./context")
    expect(original.serverStorageKey("access_token")).toBe("access_token")
    expect(localStorage.getItem(LEGACY_SERVER_KEY)).toBe(alpha.url)

    sessionStorage.clear()
    vi.stubEnv("VITE_API_URL", beta.url)
    vi.resetModules()
    const next = await import("./context")
    expect(next.serverContext().active.url).toBe(beta.url)
    expect(localStorage.getItem(next.serverStorageKey("access_token"))).toBeNull()
  })

  it("does not let a link select an unknown server", async () => {
    window.history.replaceState({}, "", "/s/token?server=" + encodeURIComponent(beta.url))
    const { serverContext } = await import("./context")
    expect(serverContext().active.url).toBe(alpha.url)
  })

  it("isolates real auth, query drafts, grid state and history, including late writes", async () => {
    const firstContext = await import("./context")
    const firstAuth = (await import("@/stores/auth")).useAuthStore()
    const firstDrafts = await import("@/features/queries/draft")
    const firstHistory = await import("@/stores/searchHistory")
    const firstGrid = await import("@/features/grid/persist")
    firstAuth.setToken("alpha-token")
    firstDrafts.writeDraft("same-id", { body: "select 'alpha'", title: null, split: 0.6, wrap: false })
    const historyKey = firstHistory.searchHistoryKey("same-user", "same-connector")
    localStorage.setItem(historyKey, '["alpha query"]')
    firstGrid.saveGridState("same-connector", "same-node", { columnOrder: ["alpha"], columnVisibility: {}, columnSizing: {}, pinnedLeft: [], filters: [], sort: [] })

    localStorage.setItem(PROFILES_KEY, JSON.stringify([beta]))
    sessionStorage.setItem(ACTIVE_SERVER_KEY, JSON.stringify(beta))
    vi.resetModules()
    setActivePinia(createPinia())
    const secondContext = await import("./context")
    const secondAuth = (await import("@/stores/auth")).useAuthStore()
    expect(secondAuth.token).toBeNull()
    expect((await import("@/features/queries/draft")).readDraft("same-id")).toBeNull()
    expect((await import("@/features/grid/persist")).loadGridState("same-connector", "same-node")).toBeNull()
    expect(localStorage.getItem((await import("@/stores/searchHistory")).searchHistoryKey("same-user", "same-connector"))).toBeNull()
    secondAuth.setToken("beta-token")

    firstAuth.setToken("late-alpha-token")
    expect(firstContext.serverContext().active.url).toBe(alpha.url)
    expect(secondContext.serverContext().active.url).toBe(beta.url)
    expect(localStorage.getItem(secondAuth.storageKey)).toBe("beta-token")
    expect(localStorage.getItem("access_token")).toBe("late-alpha-token")
    expect(secondContext.serverUrl("/api/v1/ws")).toBe(beta.url + "/api/v1/ws")
    expect(firstContext.serverUrl("/api/v1/ws")).toBe(alpha.url + "/api/v1/ws")
    expect(secondAuth.storageKey).toBe(scopedServerKey("access_token", beta.url, alpha.url))
  })
})
