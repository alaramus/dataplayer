import { useQueryClient } from "@tanstack/vue-query"

import { connectorsKey } from "@/features/connectors/api"
import { requestsKey } from "@/features/shares/api"
import { realtime } from "@/shared/realtime/client"

/**
 * Hearing that somebody asked for access, or that an ask was answered.
 *
 * The row in the database is the record; this is the tap on the shoulder, so
 * nothing here stores anything. What is missed while offline is still waiting
 * in the dialog. See D61.
 */
export const REQUESTS_TOPIC = "shares.requests"

/** One event, as the server sends it. See app/shares/topic.py. */
export interface AccessRequestEvent {
  kind: "asked" | "answered"
  request_id: string
  connector_id: string
  connector_label: string
  person: string
  outcome?: "approved" | "declined" | null
  access?: string | null
}

export function isRequestEvent(payload: unknown): payload is AccessRequestEvent {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "kind" in payload &&
    "connector_id" in payload &&
    "person" in payload
  )
}

/**
 * What to say about one event.
 *
 * Pure, so the wording is tested without a socket. A refusal is worded without
 * a reason on purpose: there is none to give, because a reason is a
 * conversation between people rather than a field in a form (D61).
 */
export function wordingOf(event: AccessRequestEvent): string {
  if (event.kind === "asked") {
    return `${event.person} is asking for access to ${event.connector_label}`
  }
  if (event.outcome === "approved") {
    const level = event.access ?? "read"
    return `${event.person} gave you ${level} access to ${event.connector_label}`
  }
  return `${event.person} did not open access to ${event.connector_label}`
}

export interface RequestEventHandlers {
  /** Somebody is waiting on a connection of yours. */
  onAsked: (event: AccessRequestEvent) => void
  /** An ask of yours was answered, one way or the other. */
  onAnswered: (event: AccessRequestEvent) => void
}

/**
 * Watch for both, for as long as the caller lives.
 *
 * Called once, from the workspace, like the health subscription beside it. The
 * queries that would now be stale are refreshed here rather than by each
 * screen: the dialog may be open in front of the person being told.
 */
export function useAccessRequestEvents(handlers: RequestEventHandlers) {
  const queryClient = useQueryClient()

  const stop = realtime().subscribe(REQUESTS_TOPIC, (payload) => {
    if (!isRequestEvent(payload)) return
    if (payload.kind === "asked") {
      void queryClient.invalidateQueries({ queryKey: requestsKey(payload.connector_id) })
      handlers.onAsked(payload)
      return
    }
    // An approval is a grant, so the list of connections has a new row in it.
    void queryClient.invalidateQueries({ queryKey: connectorsKey })
    handlers.onAnswered(payload)
  })

  return { stop }
}
