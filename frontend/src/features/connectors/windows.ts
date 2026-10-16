import { h } from "vue"
import type { Component } from "vue"

import type { ConnectorDraft, ConnectorPublic } from "@/client"
import ConnectorWindowView from "@/features/connectors/ConnectorWindow.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import { t } from "@/shared/i18n"
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

/** Preferred rectangle for every tab; overflow belongs to the form body (D132). */
export const CONNECTOR_WINDOW_SIZE = { width: 560, height: 660 }

export function connectorWindow(options: {
  id: string
  connector: ConnectorPublic | null
  adapterType: string | null
  draft?: ConnectorDraft
  onCreated: (connector: ConnectorPublic) => void
  onClose: () => void
  onBack: () => void
  onDirty: (dirty: boolean) => void
  beforeClose: () => boolean | Promise<boolean>
  /** The page to open on, for a window opened to do one thing (D61). */
  startOn?: string
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
        draft: options.draft,
        startOn: options.startOn,
        onCreated: options.onCreated,
        onClose: options.onClose,
        onBack: options.onBack,
        "onUpdate:dirty": options.onDirty,
      }),
  }

  return {
    id: options.id,
    look: {
      title: options.connector ? options.connector.name : t("connectors.new_connection"),
      icon: type ? adapterIcon(type) : undefined,
    },
    size: CONNECTOR_WINDOW_SIZE,
    sizing: "stable",
    minSize: { width: 420, height: 300 },
    beforeClose: options.beforeClose,
    component,
  }
}
