import { ref } from "vue"

import type { ConnectorPublic, NodeRepresentation, RowsView } from "@/client"

/**
 * A resolved link waiting for the workspace to open it.
 *
 * The landing screen does the asking — resolve the token, read the connection,
 * walk to the node — because it is the screen that has to explain a node that
 * is gone or a connection switched off (D60). What it cannot do is open a tab:
 * the workspace is not mounted there. So the answer is left here and taken by
 * the workspace once.
 *
 * A module ref rather than a Pinia store: stores may not reach into the
 * generated client, and this is one screen handing another the answer it
 * already has.
 */
export interface ShareIntent {
  connector: ConnectorPublic
  nodeId: string
  title: string
  describable: boolean
  representations: NodeRepresentation[]
  view: RowsView
  sharedBy: string
}

const pending = ref<ShareIntent | null>(null)

export function setShareIntent(intent: ShareIntent): void {
  pending.value = intent
}

export function takeShareIntent(): ShareIntent | null {
  const intent = pending.value
  pending.value = null
  return intent
}
