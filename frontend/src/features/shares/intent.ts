import { ref } from "vue"

import type { ConnectorPublic, NodeRepresentation, RowsView } from "@/client"

/**
 * A resolved link waiting for the workspace to open it. The landing screen
 * resolves, because it has to explain a node that is gone (D60), and cannot
 * open a tab, because the workspace is not mounted there.
 *
 * A module ref and not a Pinia store: stores may not reach into the generated
 * client, and this is one screen handing another an answer it already has.
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
