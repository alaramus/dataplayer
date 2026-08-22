import { h } from "vue"
import type { Component } from "vue"
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

export function componentOf(panel: Panel): Component {
  switch (panel.kind) {
    case "connectors":
      return ConnectorsPanelView
    case "catalog":
      // The engine renders a panel with no props of its own, so what a panel
      // needs is bound here, where the panel is still a typed object.
      return () => h(CatalogPanelView, { connectorId: panel.connectorId })
    case "rows":
      return () => h(RowsPanelView, { connectorId: panel.connectorId, nodeId: panel.nodeId })
  }
}
