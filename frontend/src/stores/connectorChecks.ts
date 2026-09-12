import { defineStore } from "pinia"
import { ref } from "vue"

/**
 * How each connection answered the last time it was checked. Pinia and not
 * vue-query (D6): the server keeps this only while somebody is watching and
 * pushes it over the socket, so it arrives unasked.
 *
 * Whether a connection is switched off is deliberately not here — that field
 * travels with the list, and one fact in two places drifts. Not persisted: a
 * dot restored from yesterday would claim more than it knows.
 */
export type CheckState = "unknown" | "ok" | "failed"

export interface CheckReport {
  ok: boolean
  message: string
  latencyMs: number | null
  checkedAt: string
}

export const useConnectorChecksStore = defineStore("connector-checks", () => {
  const results = ref<Record<string, CheckReport>>({})

  function record(connectorId: string, report: CheckReport) {
    results.value = { ...results.value, [connectorId]: report }
  }

  function reportOf(connectorId: string): CheckReport | null {
    return results.value[connectorId] ?? null
  }

  function stateOf(connectorId: string): CheckState {
    const report = results.value[connectorId]
    if (!report) return "unknown"
    return report.ok ? "ok" : "failed"
  }

  function forget(connectorId: string) {
    results.value = Object.fromEntries(
      Object.entries(results.value).filter(([id]) => id !== connectorId)
    )
  }

  /** Forget the lot: nothing is being probed any more, so nothing is known. */
  function clear() {
    results.value = {}
  }

  return { results, record, reportOf, stateOf, forget, clear }
})
