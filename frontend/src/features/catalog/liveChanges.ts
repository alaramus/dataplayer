import { getCurrentScope, onScopeDispose, watch } from "vue"

import { ConnectorsService } from "@/client"
import { realtime } from "@/shared/realtime/client"

/**
 * What changed on a connection a catalog shows, told by the source (D303).
 *
 * The catalog says which nodes it shows — the levels open in it and the tabs
 * open on that connection — again whenever that changes and every half minute,
 * since the server lets go of a watch nobody renewed. What comes back is which
 * levels and nodes to read again.
 */
export const CHANGES_TOPIC = "source.changes"

/** How often the shown nodes are said again; the server's lease is 90 s. */
const RENEW_MS = 30_000
/** How long the shown nodes settle before they are said. */
const SETTLE_MS = 400

/** One telling, as the server sends it. See app/connectors/changes.py. */
export interface SourceChangesEvent {
  connector_id: string
  levels: (string | null)[]
  nodes: string[]
  everything: boolean
}

function isChanges(payload: unknown): payload is SourceChangesEvent {
  return typeof payload === "object" && payload !== null && "connector_id" in payload && "levels" in payload
}

export interface LiveChangesOptions {
  connectorId: () => string
  /** Whether this connection's source tells changes at all. */
  live: () => boolean
  /** The nodes on screen; null is the top. */
  shown: () => (string | null)[]
  onChange: (event: SourceChangesEvent) => void
}

export function useLiveChanges(options: LiveChangesOptions) {
  let stopTopic: (() => void) | null = null
  let renew: ReturnType<typeof setInterval> | null = null
  let settle: ReturnType<typeof setTimeout> | null = null
  let followed: string | null = null

  function follow(connectorId: string, nodeIds: (string | null)[]) {
    void ConnectorsService.followChanges({
      path: { connector_id: connectorId },
      body: { node_ids: nodeIds },
    }).catch(() => {
      // Not told what changed is what every other source is; refresh by hand.
    })
  }

  function stop() {
    if (settle !== null) clearTimeout(settle)
    if (renew !== null) clearInterval(renew)
    settle = null
    renew = null
    stopTopic?.()
    stopTopic = null
    if (followed !== null) follow(followed, [])
    followed = null
  }

  function start(connectorId: string) {
    followed = connectorId
    stopTopic = realtime().subscribe(CHANGES_TOPIC, (payload) => {
      if (isChanges(payload) && payload.connector_id === connectorId) options.onChange(payload)
    })
    renew = setInterval(() => follow(connectorId, options.shown()), RENEW_MS)
  }

  watch(
    () => (options.live() ? options.connectorId() : null),
    (connectorId) => {
      stop()
      if (connectorId !== null) start(connectorId)
    },
    { immediate: true }
  )

  watch(
    () => (followed === null || !options.live() ? null : JSON.stringify(options.shown())),
    (shown) => {
      if (shown === null || followed === null) return
      const connectorId = followed
      if (settle !== null) clearTimeout(settle)
      settle = setTimeout(() => follow(connectorId, options.shown()), SETTLE_MS)
    },
    { immediate: true }
  )

  if (getCurrentScope()) onScopeDispose(stop)
}
