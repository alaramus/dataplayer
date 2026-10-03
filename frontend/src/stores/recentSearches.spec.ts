import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

import { serverStorageKey } from "@/shared/servers/context"

import { parseRecent, RECENT_SEARCHES_LIMIT, useRecentSearchesStore, withRecent } from "./recentSearches"

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  setActivePinia(createPinia())
})

describe("recent searches", () => {
  it("keeps the last ten distinct searches, a repeat moved to the front", () => {
    const store = useRecentSearchesStore()
    for (let index = 0; index < 12; index++) store.remember(`words ${index}`)
    store.remember("  words 3  ")
    store.remember("   ")
    expect(store.entries).toHaveLength(RECENT_SEARCHES_LIMIT)
    expect(store.entries.slice(0, 3)).toEqual(["words 3", "words 11", "words 10"])
  })

  it("lives in this tab's session storage and never in local storage", () => {
    useRecentSearchesStore().remember("orders")
    expect(JSON.parse(sessionStorage.getItem(serverStorageKey("dp.search.recent")) ?? "[]")).toEqual([
      "orders",
    ])
    expect(localStorage.length).toBe(0)
  })

  it("comes back in a page reloaded in the same tab", () => {
    useRecentSearchesStore().remember("orders")
    setActivePinia(createPinia())
    expect(useRecentSearchesStore().entries).toEqual(["orders"])
  })

  it("forgets words that must not be kept", () => {
    const store = useRecentSearchesStore()
    store.remember("orders")
    store.remember("select secret")
    store.forget(" select secret ")
    expect(store.entries).toEqual(["orders"])
  })

  it("is emptied whole, storage included, on sign-out", () => {
    const store = useRecentSearchesStore()
    store.remember("orders")
    store.clear()
    expect(store.entries).toEqual([])
    expect(sessionStorage.getItem(serverStorageKey("dp.search.recent"))).toBeNull()
  })

  it("reads a damaged value as nothing rather than failing", () => {
    expect(parseRecent("{not json")).toEqual([])
    expect(parseRecent('{"a": 1}')).toEqual([])
    expect(parseRecent('["a", 3, " ", "a", "b"]')).toEqual(["a", "b"])
  })

  it("puts the newest first, once", () => {
    expect(withRecent(["a", "b"], "b")).toEqual(["b", "a"])
    expect(withRecent(["a"], "  ")).toEqual(["a"])
  })
})
