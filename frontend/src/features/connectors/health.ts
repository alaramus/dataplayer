import { getCurrentScope, onScopeDispose, watch } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { realtime } from "@/shared/realtime/client"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

/**
 * The state of every connection, kept up to date without being asked for.
 *
 * The server probes only while somebody is watching, so subscribing is what
 * makes it happen at all; dropping the subscription is what makes it stop.
 */
export const HEALTH_TOPIC = "connector.health"

/** One report, as the server sends it. See app/connectors/health.py. */
export interface ConnectorHealthEvent {
  connector_id: string
  result: {
    ok: boolean
    message: string
    latency_ms: number | null
    error_kind: string | null
  }
  checked_at: string
}

interface WatchedConnector {
  id: string
  enabled: boolean
}

/**
 * Which remembered results may no longer be shown.
 *
 * A connection that is gone, and a connection that was switched off: the
 * server stops probing the second one, so what it last said stops being true
 * of it. Pure, so the rule is tested without a socket or a store.
 */
export function staleChecks(known: string[], connectors: WatchedConnector[]): string[] {
  const live = new Set(
    connectors.filter((connector) => connector.enabled).map((connector) => connector.id)
  )
  return known.filter((id) => !live.has(id))
}

function isHealthEvent(payload: unknown): payload is ConnectorHealthEvent {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "connector_id" in payload &&
    "result" in payload
  )
}

/**
 * Watch the state of this user's connections for as long as the caller lives.
 *
 * Called once, from the workspace: a second caller would be a second
 * subscription to the same topic, which the socket handles, but there is no
 * screen that needs one.
 */
export function useConnectorHealth() {
  const checks = useConnectorChecksStore()
  const connectors = useConnectors()

  const stop = realtime().subscribe(HEALTH_TOPIC, (payload) => {
    if (!isHealthEvent(payload)) return
    checks.record(payload.connector_id, {
      ok: payload.result.ok,
      message: payload.result.message,
      latencyMs: payload.result.latency_ms,
      checkedAt: payload.checked_at,
    })
  })

  watch(
    connectors.data,
    (list) => {
      const gone = staleChecks(
        Object.keys(checks.results),
        (list?.data ?? []).map((connector) => ({
          id: connector.id,
          enabled: connector.enabled,
        }))
      )
      for (const id of gone) checks.forget(id)
    },
    { deep: true }
  )

  // Released with the component that asked, for the reason the requests topic
  // gives: a listener outliving its screen is a second copy of every event.
  if (getCurrentScope()) onScopeDispose(stop)

  return { stop }
}
