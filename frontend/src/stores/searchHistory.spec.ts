import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { searchHistoryKey, useSearchHistoryStore } from "./searchHistory"

const key = searchHistoryKey("alice", "files")

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})
afterEach(() => vi.unstubAllGlobals())

describe("catalog search history", () => {
  it("keeps the last ten distinct queries, moving a repeat to the front", () => {
    const store = useSearchHistoryStore()
    for (let index = 0; index < 12; index++) store.remember(key, `query ${index}`)
    store.remember(key, "  query 3  ")
    store.remember(key, "   ")

    expect(store.byKey[key]).toEqual([
      "query 3", "query 11", "query 10", "query 9", "query 8",
      "query 7", "query 6", "query 5", "query 4", "query 2",
    ])
  })

  it("restores saved queries and deletions in a new session", () => {
    const store = useSearchHistoryStore()
    store.remember(key, "notes")
    store.remember(key, "reports")
    store.remove(key, "notes")

    setActivePinia(createPinia())
    const restored = useSearchHistoryStore()
    expect(restored.load(key)).toEqual(["reports"])
    restored.remove(key, "reports")
    expect(localStorage.getItem(key)).toBeNull()
  })

  it("separates connectors and accounts, including a shared connector", () => {
    const store = useSearchHistoryStore()
    const otherConnector = searchHistoryKey("alice", "database")
    const otherUser = searchHistoryKey("bob", "files")
    store.remember(key, "notes")
    store.remember(otherConnector, "orders")
    store.remember(otherUser, "invoices")
    store.remove(otherUser, "invoices")

    expect(store.load(key)).toEqual(["notes"])
    expect(store.load(otherConnector)).toEqual(["orders"])
    expect(store.load(otherUser)).toEqual([])
    expect(searchHistoryKey("a:b", "c")).not.toBe(searchHistoryKey("a", "b:c"))
  })

  it.each(["{broken", "null", '{"queries":["notes"]}'])(
    "ignores an unusable stored value: %s",
    (raw) => {
      localStorage.setItem(key, raw)
      expect(useSearchHistoryStore().load(key)).toEqual([])
    }
  )

  it("normalizes stored entries and enforces the limit when restoring", () => {
    localStorage.setItem(key, JSON.stringify([
      " notes ", null, 42, {}, "", "notes",
      ...Array.from({ length: 12 }, (_, index) => `query ${index}`),
    ]))
    expect(useSearchHistoryStore().load(key)).toEqual([
      "notes", "query 0", "query 1", "query 2", "query 3",
      "query 4", "query 5", "query 6", "query 7", "query 8",
    ])
  })

  it("keeps history usable in memory when browser storage is blocked", () => {
    const unavailable = () => { throw new Error("Storage blocked") }
    vi.stubGlobal("localStorage", {
      getItem: unavailable, setItem: unavailable, removeItem: unavailable,
    })
    const store = useSearchHistoryStore()
    expect(store.load(key)).toEqual([])
    store.remember(key, "notes")
    expect(store.byKey[key]).toEqual(["notes"])
    store.remove(key, "notes")
    expect(store.byKey[key]).toEqual([])
  })
})
