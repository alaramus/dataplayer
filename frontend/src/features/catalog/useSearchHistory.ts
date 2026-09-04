import { computed, watch } from "vue"
import type { Ref } from "vue"

import { searchHistoryKey, useSearchHistoryStore } from "@/stores/searchHistory"

export function useSearchHistory(
  userId: Ref<string | null>,
  connectorId: Ref<string>,
  filter: Ref<string>
) {
  const store = useSearchHistoryStore()
  const key = computed(() =>
    userId.value === null ? null : searchHistoryKey(userId.value, connectorId.value)
  )
  let edited = false

  watch(
    key,
    (next) => {
      edited = false
      if (next !== null) store.load(next)
    },
    { immediate: true, flush: "sync" }
  )
  watch(filter, () => { edited = true }, { flush: "sync" })

  const entries = computed(() => key.value === null ? [] : (store.byKey[key.value] ?? []))

  /** Blur saves edits; an explicit search or selection also refreshes recency. */
  function remember(explicit = false) {
    if (key.value === null || (!edited && !explicit)) return
    store.remember(key.value, filter.value)
    edited = false
  }

  function select(query: string) {
    filter.value = query
    remember(true)
  }

  function remove(query: string) {
    if (key.value === null) return
    store.remove(key.value, query)
    // Leaving an unchanged field must not undo a deliberate deletion.
    if (filter.value.trim() === query) edited = false
  }

  return { entries, remember, select, remove }
}
