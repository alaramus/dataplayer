import { useQueryClient } from "@tanstack/vue-query"
import { getCurrentScope, onScopeDispose } from "vue"

import { connectorsKey } from "@/features/connectors/api"
import { requestsKey } from "@/features/shares/api"
import { waitingKey } from "@/features/shares/attention"
import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"
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
  const said = { person: event.person, connector: event.connector_label }
  if (event.kind === "asked") return t("shares.requests.asked", said)
  if (event.outcome === "approved") {
    return t("shares.requests.approved", { ...said, level: levelWord(event.access ?? "read") })
  }
  return t("shares.requests.declined", said)
}

const LEVEL_WORDS: Record<string, MessageKey> = {
  read: "shares.levels.read",
  write: "shares.levels.write",
  structure: "shares.levels.structure",
}

/** A level as the sentence names it; one this build does not know, as sent. */
function levelWord(level: string): string {
  const key = LEVEL_WORDS[level]
  return key === undefined ? level : t(key)
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
      void queryClient.invalidateQueries({ queryKey: waitingKey })
      handlers.onAsked(payload)
      return
    }
    // An approval is a grant, so the list of connections has a new row in it.
    void queryClient.invalidateQueries({ queryKey: connectorsKey })
    handlers.onAnswered(payload)
  })

  // Released with the component that asked. A caller mounted twice — which
  // the workspace is, briefly, while the server check settles — otherwise
  // leaves a listener behind, and the second copy of a message is then said
  // by a screen that no longer exists.
  if (getCurrentScope()) onScopeDispose(stop)

  return { stop }
}
