import { defineStore } from "pinia"
import { ref } from "vue"

/**
 * That something changed the structure of a connection, and when.
 *
 * A moment in time, so a panel that built its own list can notice it is out of
 * date: the catalog keeps its rows in a ref rather than in the query cache, so
 * emptying that cache is not enough, and a console that dropped a table is in
 * another panel entirely (D66). What changed is not said here.
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
