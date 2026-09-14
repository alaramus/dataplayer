import { computed } from "vue"
import type { ComputedRef } from "vue"

import type { HostRestarts } from "@/client"
import type { AttentionItem } from "@/shared/notifications"
import { useSpaceStore } from "@/stores/space"

import { useRestarts } from "./api"

/**
 * A host of one's agents that keeps restarting (D115, D130).
 *
 * Not dismissible: it is a state, not news, and it goes by itself once the
 * host has stopped restarting for the window the server counts over.
 */

export function restartItem(
  restarts: HostRestarts,
  windowSeconds: number,
  openDashboards: () => void
): AttentionItem {
  const minutes = Math.round(windowSeconds / 60)
  const times = `${String(restarts.count)} times in the last ${String(minutes)} minutes`
  const detail = restarts.cause === "host"
    ? `The host booted ${times}, by what ${restarts.agent_name} reports.`
    : `The agent ${restarts.agent_name} started again ${times}; its log says why.`
  return {
    id: `restarts:${restarts.agent_id}:${restarts.host}`,
    tone: "warning",
    title: `${restarts.host} keeps restarting`,
    detail,
    at: Date.parse(restarts.last_at) || Date.now(),
    action: { label: "Open Dashboards", run: openDashboards },
    dismiss: null,
  }
}

export function useRestartAttention(): ComputedRef<AttentionItem[]> {
  const restarts = useRestarts()
  const space = useSpaceStore()
  return computed(() => {
    const answer = restarts.data.value
    if (answer === undefined) return []
    return answer.hosts.map((host) => restartItem(host, answer.window_seconds, () => { space.show("dashboards") }))
  })
}
