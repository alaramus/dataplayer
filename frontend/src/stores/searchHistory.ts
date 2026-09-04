import { defineStore } from "pinia"
import { ref } from "vue"
import { serverStorageKey } from "@/shared/servers/context"

export const SEARCH_HISTORY_LIMIT = 10

export function searchHistoryKey(userId: string, connectorId: string): string {
  return serverStorageKey(`dataplayer-search-history:v1:${JSON.stringify([userId, connectorId])}`)
}

function parseHistory(raw: string | null): string[] {
  if (raw === null) return []
  const value: unknown = JSON.parse(raw)
  if (!Array.isArray(value)) return []
  const queries = value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter((item) => item !== "")
  return [...new Set(queries)].slice(0, SEARCH_HISTORY_LIMIT)
}

/** Browser-owned history, shared by panels but separated by account and connector. */
export const useSearchHistoryStore = defineStore("searchHistory", () => {
  const byKey = ref<Record<string, string[]>>({})

  function load(key: string): string[] {
    const cached = byKey.value[key]
    if (cached !== undefined) return cached
    let entries: string[] = []
    try {
      entries = parseHistory(localStorage.getItem(key))
    } catch {
      // Unavailable or damaged browser storage must not prevent filtering.
    }
    byKey.value[key] = entries
    return entries
  }

  function save(key: string, entries: string[]) {
    byKey.value[key] = entries
    try {
      if (entries.length === 0) localStorage.removeItem(key)
      else localStorage.setItem(key, JSON.stringify(entries))
    } catch {
      // Keep this session's history usable when browser storage is full or blocked.
    }
  }

  function remember(key: string, text: string) {
    const query = text.trim()
    if (query === "") return
    save(key, [query, ...load(key).filter((item) => item !== query)].slice(0, SEARCH_HISTORY_LIMIT))
  }

  function remove(key: string, query: string) {
    save(key, load(key).filter((item) => item !== query))
  }

  return { byKey, load, remember, remove }
})
