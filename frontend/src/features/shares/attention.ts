import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { ComputedRef } from "vue"

import { SharesService } from "@/client"
import type { AccessRequestPublic } from "@/client"
import type { AttentionItem } from "@/shared/notifications"

/**
 * Who is waiting for an answer, across every connection this person owns.
 *
 * A request is the clearest case of something that will not resolve itself
 * (D115): it was durable before this sheet existed, and the only thing that
 * ends it is somebody deciding. So it carries no dismissal — waving it away
 * would leave the other person waiting with nobody left to notice.
 */

export const waitingKey = ["shares", "waiting-on-me"] as const

export function useWaitingRequests() {
  return useQuery({
    queryKey: waitingKey,
    queryFn: async () => (await SharesService.listRequests({})).data,
    // Slower than the jobs listing: the socket says when one arrives, and this
    // is the floor under a message that never came.
    refetchInterval: 60_000,
  })
}

export function requestItem(
  asked: AccessRequestPublic,
  answer: (connectorId: string) => void
): AttentionItem {
  const who = asked.requester_name ?? asked.requester_email
  return {
    id: `access:${asked.id}`,
    tone: "info",
    title: `${who} is asking for access to ${asked.connector_label}`,
    detail: asked.node_label === null || asked.node_label === undefined
      ? "Through a link to the connection"
      : `Through a link to ${asked.node_label}`,
    at: Date.parse(asked.created_at ?? "") || Date.now(),
    // Answered where grants are given, not here (D61, D113).
    action: { label: "Open", run: () => { answer(asked.connector_id) } },
    dismiss: null,
  }
}

export function useAccessAttention(
  answer: (connectorId: string) => void
): ComputedRef<AttentionItem[]> {
  const waiting = useWaitingRequests()
  return computed(() => (waiting.data.value?.data ?? []).map((asked) => requestItem(asked, answer)))
}
