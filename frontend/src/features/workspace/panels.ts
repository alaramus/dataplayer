import { defineComponent, h } from "vue"
import type { Component, VNode } from "vue"
import { z } from "zod"

import CatalogPanelView from "@/features/workspace/panels/CatalogPanel.vue"
import ConnectorsPanelView from "@/features/workspace/panels/ConnectorsPanel.vue"
import RowsPanelView from "@/features/workspace/panels/RowsPanel.vue"
import type { PanelLook } from "@/shared/workspace"

/**
 * What a panel is, and what renders it.
 *
 * The union is closed and the registry covers every member, so adding a kind
 * without a component fails to compile and fails the test beside this file.
 * The engine sees none of this — see the spec, W1.
 */

export const panelSchema = z.discriminatedUnion("kind", [
  z.object({ id: z.string(), kind: z.literal("connectors") }),
  z.object({
    id: z.string(),
    kind: z.literal("catalog"),
    connectorId: z.string(),
    title: z.string(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("rows"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
  }),
])

export type Panel = z.infer<typeof panelSchema>
export type PanelKind = Panel["kind"]

/**
 * A panel is identified by what it shows.
 *
 * Opening the same table twice then activates the tab that is already there
 * rather than putting a second copy of it beside the first.
 */
export const catalogPanelId = (connectorId: string) => `catalog:${connectorId}`
export const rowsPanelId = (connectorId: string, nodeId: string) => `rows:${connectorId}:${nodeId}`

export function kindOf(panel: Panel): PanelKind {
  return panel.kind
}

export function lookOf(panel: Panel): PanelLook {
  switch (panel.kind) {
    case "connectors":
      return { title: "Connections", icon: "lan" }
    case "catalog":
      return { title: panel.title, icon: "account_tree" }
    case "rows":
      return { title: panel.title, icon: "table_chart" }
  }
}

/**
 * One bound component per panel, kept.
 *
 * The engine asks for the component of the active panel on every render, and
 * Vue tells two components apart by identity: a wrapper built afresh each time
 * is a different type each time, so the panel would be torn down and mounted
 * again on every render of the section — reloading the catalog and losing the
 * page the grid was on. The key is the id of the panel, which already names
 * what the panel shows, so a stale entry is the component it would rebuild.
 *
 * A component and not a render function: a functional component has no
 * instance, so <KeepAlive> in the section would have nothing to keep and a tab
 * switched away from would come back reloaded.
 */
const bound = new Map<string, Component>()

function boundComponent(id: string, render: () => VNode): Component {
  const kept = bound.get(id)
  if (kept !== undefined) return kept
  const made = defineComponent({ name: `PanelBinding-${id}`, setup: () => render })
  bound.set(id, made)
  return made
}

export function componentOf(panel: Panel): Component {
  switch (panel.kind) {
    case "connectors":
      return ConnectorsPanelView
    case "catalog":
      // The engine renders a panel with no props of its own, so what a panel
      // needs is bound here, where the panel is still a typed object.
      return boundComponent(panel.id, () => h(CatalogPanelView, { connectorId: panel.connectorId }))
    case "rows":
      return boundComponent(panel.id, () =>
        h(RowsPanelView, { connectorId: panel.connectorId, nodeId: panel.nodeId })
      )
  }
}
