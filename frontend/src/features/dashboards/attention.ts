import { computed } from "vue"
import type { ComputedRef } from "vue"

import type { HostRestarts } from "@/client"
import { t } from "@/shared/i18n"
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
  const times = t("dashboards.restarts.times", { n: restarts.count, minutes }, restarts.count)
  const detail = restarts.cause === "host"
    ? t("dashboards.restarts.host", { times, agent: restarts.agent_name })
    : t("dashboards.restarts.agent", { agent: restarts.agent_name, times })
  return {
    id: `restarts:${restarts.agent_id}:${restarts.host}`,
    tone: "warning",
    title: t("dashboards.restarts.title", { host: restarts.host }),
    detail,
    at: Date.parse(restarts.last_at) || Date.now(),
    action: { label: t("dashboards.restarts.open"), run: openDashboards },
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
