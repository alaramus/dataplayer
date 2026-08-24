import { defineStore } from "pinia"
import { ref } from "vue"

/**
 * How each connection answered the last time it was checked.
 *
 * Client state, so Pinia and not vue-query (D6). Not because the server has no
 * such record — while the screen is open it keeps one, and pushes it over the
 * socket — but because vue-query is for state that is fetched and invalidated,
 * and this arrives unasked. What the server holds it holds only for as long as
 * somebody is watching, and this is the mirror of that.
 *
 * Whether a connection is switched off is deliberately not here: that is a
 * field of the connector and travels with the list. One fact in two places
 * drifts apart.
 *
 * Deliberately not persisted: a check tells you about a server a minute ago,
 * and a dot restored from yesterday would claim more than it knows.
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

  return { results, record, reportOf, stateOf, forget }
})
