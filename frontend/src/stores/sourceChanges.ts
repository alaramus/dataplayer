import { defineStore } from "pinia"
import { ref } from "vue"

/**
 * That something changed the structure of a connection, and when.
 *
 * Not a cache and not server state: a moment in time, so a panel that built
 * its own list can notice that the list is out of date. The catalog column
 * keeps its rows in a ref rather than reading them through vue-query, so
 * emptying the query cache is not enough to make it re-read — and a console
 * that has just dropped a table is in another panel entirely (D66).
 *
 * What changed is not said here. The source already said that, and whoever
 * applies its answer to the query cache has it; this is only the nudge.
 */
export const useSourceChangesStore = defineStore("sourceChanges", () => {
  const changedAt = ref<Record<string, number>>({})

  function announce(connectorId: string) {
    // A new object rather than a mutated one, so a watcher on one connection's
    // entry sees the change without watching the whole map deeply.
    changedAt.value = { ...changedAt.value, [connectorId]: Date.now() }
  }

  function lastChange(connectorId: string): number {
    return changedAt.value[connectorId] ?? 0
  }

  return { changedAt, announce, lastChange }
})
