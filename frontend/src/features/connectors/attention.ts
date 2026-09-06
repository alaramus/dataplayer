import { computed, ref } from "vue"
import type { ComputedRef } from "vue"

import { useConnectors } from "@/features/connectors/api"
import type { AttentionItem } from "@/shared/notifications"
import { useConnectorChecksStore } from "@/stores/connectorChecks"
import type { CheckReport } from "@/stores/connectorChecks"

/**
 * A connection that answered badly the last time anybody asked (D115).
 *
 * Reports what is already known and starts nothing: the server probes only
 * while a screen is watching (D18), so this source is honest about being a
 * view over the last thing heard rather than a monitor.
 */

export function checkItem(
  connectorId: string,
  name: string,
  report: CheckReport,
  open: (connectorId: string) => void,
  dismiss: () => void
): AttentionItem {
  return {
    id: `check:${connectorId}:${report.checkedAt}`,
    tone: "error",
    title: `${name} is not answering`,
    detail: report.message,
    at: Date.parse(report.checkedAt) || Date.now(),
    action: { label: "Open", run: () => { open(connectorId) } },
    // Waved away by the report it was about, so the next bad answer from the
    // same connection is news again.
    dismiss,
  }
}

export function useHealthAttention(
  open: (connectorId: string) => void
): ComputedRef<AttentionItem[]> {
  const checks = useConnectorChecksStore()
  const connectors = useConnectors()
  const waved = ref(new Set<string>())

  return computed(() => Object.entries(checks.results)
    .filter(([, report]) => !report.ok)
    .flatMap(([connectorId, report]) => {
      const found = connectors.data.value?.data.find((connector) => connector.id === connectorId)
      if (found === undefined) return []
      const key = `${connectorId}:${report.checkedAt}`
      if (waved.value.has(key)) return []
      return [checkItem(connectorId, found.name, report, open, () => {
        waved.value = new Set([...waved.value, key])
      })]
    }))
}
