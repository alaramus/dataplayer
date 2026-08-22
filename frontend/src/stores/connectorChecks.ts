import { defineStore } from "pinia"
import { ref } from "vue"

/**
 * How each connection answered the last time the user checked it.
 *
 * Client state, so Pinia and not vue-query (D6): the server holds no such
 * record, and asking it for one would mean opening a connection to every
 * source the moment the screen loads — N connections to other people's
 * servers for the sake of a coloured dot. Nothing checked is a state of its
 * own, and the dot says so.
 *
 * Deliberately not persisted: a check tells you about a server a minute ago,
 * and a dot restored from yesterday would claim more than it knows.
 */
export type CheckState = "unknown" | "ok" | "failed"

export const useConnectorChecksStore = defineStore("connector-checks", () => {
  const results = ref<Record<string, Exclude<CheckState, "unknown">>>({})

  function record(connectorId: string, ok: boolean) {
    results.value = { ...results.value, [connectorId]: ok ? "ok" : "failed" }
  }

  function stateOf(connectorId: string): CheckState {
    return results.value[connectorId] ?? "unknown"
  }

  function forget(connectorId: string) {
    results.value = Object.fromEntries(
      Object.entries(results.value).filter(([id]) => id !== connectorId)
    )
  }

  return { results, record, stateOf, forget }
})
