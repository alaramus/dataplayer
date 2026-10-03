import { defineStore } from "pinia"
import { ref } from "vue"

import { serverStorageKey } from "@/shared/servers/context"

/** How many submitted searches the field offers back while it is empty (D205). */
export const RECENT_SEARCHES_LIMIT = 10

const KEY = "dp.search.recent"

/**
 * What was looked for, newest first, without repeats or blanks.
 *
 * Read defensively: the value is this tab's own, but a damaged one must cost
 * the list and nothing else.
 */
export function parseRecent(raw: string | null): string[] {
  if (raw === null) return []
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(value)) return []
  const words = value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter((item) => item !== "")
  return [...new Set(words)].slice(0, RECENT_SEARCHES_LIMIT)
}

/** The list with these words first, once. */
export function withRecent(entries: readonly string[], words: string): string[] {
  const typed = words.trim()
  if (typed === "") return [...entries]
  return [typed, ...entries.filter((item) => item !== typed)].slice(0, RECENT_SEARCHES_LIMIT)
}

function read(): string[] {
  try {
    return parseRecent(sessionStorage.getItem(serverStorageKey(KEY)))
  } catch {
    return []
  }
}

/**
 * The last ten searches submitted in this browser tab (D205).
 *
 * Session storage, as D63 keeps a console's draft: it dies with the tab, so
 * this never becomes a durable record of what somebody looked for. Never in
 * local storage, and emptied on sign-out.
 */
export const useRecentSearchesStore = defineStore("recentSearches", () => {
  const entries = ref<string[]>(read())

  function write(next: string[]) {
    entries.value = next
    try {
      if (next.length === 0) sessionStorage.removeItem(serverStorageKey(KEY))
      else sessionStorage.setItem(serverStorageKey(KEY), JSON.stringify(next))
    } catch {
      // A tab with no storage left keeps the list for as long as it is open.
    }
  }

  function remember(words: string) {
    write(withRecent(entries.value, words))
  }

  /** Words that must not be kept: a search that found a saved query's text. */
  function forget(words: string) {
    const typed = words.trim()
    write(entries.value.filter((item) => item !== typed))
  }

  function clear() {
    write([])
  }

  return { entries, remember, forget, clear }
})
