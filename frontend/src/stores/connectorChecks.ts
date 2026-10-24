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

/** A connection that answered and then stopped: when the first bad answer came. */
export interface Outage {
  since: string
}

/** A connection whose outage ended, as news for whoever tells people. */
export interface Recovery {
  connectorId: string
  at: string
}

export const useConnectorChecksStore = defineStore("connector-checks", () => {
  const results = ref<Record<string, CheckReport>>({})
  /**
   * Outages, by connection: a change from answering to not, not every bad
   * answer (D115). A connection that has not answered since this tab first
   * heard of it has none — it was saved broken, or broke while nobody was
   * looking, and its dot says so without a notification every few minutes.
   */
  const outages = ref<Record<string, Outage>>({})
  const recoveries = ref<Recovery[]>([])
  // Outlives `clear`: the probes stop when nobody watches, and a connection
  // that answered before that is still one that answered.
  const answered = new Set<string>()

  function record(connectorId: string, report: CheckReport) {
    results.value = { ...results.value, [connectorId]: report }
    const outage = outages.value[connectorId]
    if (report.ok) {
      answered.add(connectorId)
      if (outage !== undefined) {
        outages.value = without(outages.value, connectorId)
        recoveries.value = [...recoveries.value, { connectorId, at: report.checkedAt }]
      }
    } else if (outage === undefined && answered.has(connectorId)) {
      outages.value = { ...outages.value, [connectorId]: { since: report.checkedAt } }
    }
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
    results.value = without(results.value, connectorId)
    outages.value = without(outages.value, connectorId)
    answered.delete(connectorId)
  }

  /** Forget the lot: nothing is being probed any more, so nothing is known. */
  function clear() {
    results.value = {}
  }

  return { results, outages, recoveries, record, reportOf, stateOf, forget, clear }
})

function without<T>(map: Record<string, T>, key: string): Record<string, T> {
  return Object.fromEntries(Object.entries(map).filter(([id]) => id !== key))
}
