import { computed, ref, watch } from "vue"
import type { ComputedRef } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { t } from "@/shared/i18n"
import type { AttentionItem } from "@/shared/notifications"
import { useToast } from "@/shared/ui"
import { useConnectorChecksStore } from "@/stores/connectorChecks"
import type { Outage } from "@/stores/connectorChecks"

/**
 * A connection that answered and then stopped (D115).
 *
 * One item per outage, not per bad answer: the server probes every few
 * minutes while a screen watches (D18), and an item per probe was a new
 * notification every few minutes about one fact. A connection that never
 * answered in this tab has no outage — its dot says it is down.
 */

export function outageItem(
  connectorId: string,
  name: string,
  outage: Outage,
  detail: string,
  open: (connectorId: string) => void,
  dismiss: () => void
): AttentionItem {
  return {
    id: `check:${connectorId}:${outage.since}`,
    tone: "error",
    title: t("connectors.attention.not_answering", { name }),
    detail,
    at: Date.parse(outage.since) || Date.now(),
    action: { label: t("connectors.attention.open"), run: () => { open(connectorId) } },
    // Waved away for this outage, so the next one is news again.
    dismiss,
  }
}

export function useHealthAttention(
  open: (connectorId: string) => void
): ComputedRef<AttentionItem[]> {
  const checks = useConnectorChecksStore()
  const connectors = useConnectors()
  const toast = useToast()
  const waved = ref(new Set<string>())

  const nameOf = (connectorId: string) =>
    connectors.data.value?.data.find((connector) => connector.id === connectorId)?.name

  // An outage ending is one line in Recent, not something waiting for anybody.
  let told = checks.recoveries.length
  watch(
    () => checks.recoveries.length,
    (length) => {
      for (const recovery of checks.recoveries.slice(told, length)) {
        const name = nameOf(recovery.connectorId)
        if (name !== undefined) toast.success(t("connectors.attention.answering_again", { name }))
      }
      told = length
    }
  )

  return computed(() => Object.entries(checks.outages)
    .flatMap(([connectorId, outage]) => {
      const name = nameOf(connectorId)
      if (name === undefined) return []
      const key = `${connectorId}:${outage.since}`
      if (waved.value.has(key)) return []
      return [outageItem(connectorId, name, outage, checks.results[connectorId]?.message ?? "", open, () => {
        waved.value = new Set([...waved.value, key])
      })]
    }))
}
