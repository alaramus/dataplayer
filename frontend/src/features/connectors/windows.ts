import { h } from "vue"
import type { Component } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorWindowView from "@/features/connectors/ConnectorWindow.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import type { OpenWindow } from "@/shared/windows"

/**
 * What a connection window is called and how big it opens.
 *
 * A window is identified by what it shows, the way a panel is: opening the
 * same connection twice brings the one already open to the front rather than
 * making a second copy of it. Two windows of one row are two unsaved edits of
 * that row, and whichever is saved second silently wins. See the spec, O2.
 */
export const connectorWindowId = (connectorId: string) => `connector:${connectorId}`

/** A draft has no row to overwrite, so any number of them may be open. */
let drafts = 0
export const draftWindowId = () => `connector:new:${(drafts += 1)}`

/**
 * Wide enough for an address on one line, tall enough for the whole form.
 *
 * The height is not a guess: at 520 the connection string fell below the fold
 * of the scrolling body, and it is one of the things this window exists to
 * show. `place` shrinks the window to a viewport that cannot hold it.
 */
export const CONNECTOR_WINDOW_SIZE = { width: 560, height: 660 }

export function connectorWindow(options: {
  id: string
  connector: ConnectorPublic | null
  adapterType: string | null
  onCreated: (connector: ConnectorPublic) => void
  onClose: () => void
  onBack: () => void
  onDirty: (dirty: boolean) => void
}): OpenWindow {
  const type = options.connector?.adapter_type ?? options.adapterType ?? null

  // Bound here, where the window is still a typed thing: the engine renders a
  // component with no props of its own.
  const component: Component = {
    name: `ConnectorWindow-${options.id}`,
    setup: () => () =>
      h(ConnectorWindowView, {
        connector: options.connector,
        adapterType: options.adapterType,
        onCreated: options.onCreated,
        onClose: options.onClose,
        onBack: options.onBack,
        "onUpdate:dirty": options.onDirty,
      }),
  }

  return {
    id: options.id,
    look: {
      title: options.connector ? options.connector.name : "New connection",
      icon: type ? adapterIcon(type) : undefined,
    },
    size: CONNECTOR_WINDOW_SIZE,
    component,
  }
}
