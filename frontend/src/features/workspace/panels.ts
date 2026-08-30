import { defineComponent, h } from "vue"
import type { Component, VNode } from "vue"
import { z } from "zod"

import ChartPanelView from "@/features/charts/ChartPanel.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import CatalogPanelView from "@/features/workspace/panels/CatalogPanel.vue"
import ConnectorRailView from "@/features/workspace/panels/ConnectorRail.vue"
import ConnectorsPanelView from "@/features/workspace/panels/ConnectorsPanel.vue"
import RowsPanelView from "@/features/workspace/panels/RowsPanel.vue"
import StructurePanelView from "@/features/workspace/panels/StructurePanel.vue"
import WorkspaceSceneView from "@/features/workspace/panels/WorkspaceScene.vue"
import type { PanelLook } from "@/shared/workspace"

const scalarFilterSchema = z.object({
  column: z.string(),
  op: z.enum(["eq", "ne", "gt", "gte", "lt", "lte", "contains", "starts_with"]),
  value: z.string(),
})
const inFilterSchema = z.object({
  column: z.string(),
  op: z.literal("in"),
  values: z.array(z.string()),
})
const nullFilterSchema = z.object({
  column: z.string(),
  op: z.enum(["is_null", "is_not_null"]),
})
const fetchRequestSchema = z.object({
  node_id: z.string(),
  limit: z.number().int().positive().max(500).optional(),
  offset: z.number().int().nonnegative().optional(),
  filters: z.array(z.union([scalarFilterSchema, inFilterSchema, nullFilterSchema])).optional(),
  sort: z.array(z.object({ column: z.string(), descending: z.boolean().optional() })).optional(),
})

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
    // Carried on the panel so a catalog restored from storage can draw the
    // icon of its source before the list of connections has been read.
    adapterType: z.string(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("rows"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
    // Both carried on the panel for the reason the catalog carries its type:
    // a layout restored from storage draws the tab before the list of
    // connections has been read. See P8.
    connectorName: z.string(),
    adapterType: z.string(),
    // Optional so a layout saved before D28 still restores. It gains the
    // source-declared value the next time the node is opened from its catalog.
    describable: z.boolean().optional(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("structure"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
    connectorName: z.string(),
    adapterType: z.string(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("chart"),
    viewKey: z.string(),
    connectorId: z.string(),
    title: z.string(),
    connectorName: z.string(),
    adapterType: z.string(),
    request: fetchRequestSchema,
    columns: z
      .array(z.string().min(1))
      .min(1)
      .refine((names) => new Set(names).size === names.length, "Columns must be distinct"),
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
export const structurePanelId = (connectorId: string, nodeId: string) =>
  `structure:${connectorId}:${nodeId}`
export const chartPanelId = (viewKey: string) => `chart:${viewKey}`

export function kindOf(panel: Panel): PanelKind {
  return panel.kind
}

/**
 * The connections that have a catalog open.
 *
 * A row of the list is now in one of two states — open, and the one being
 * looked at — and the first of them is a fact about the panels rather than
 * about the tree. See P7.
 */
export function openConnectorIds(panels: Panel[]): Set<string> {
  return new Set(
    panels.filter((panel) => panel.kind === "catalog").map((panel) => panel.connectorId)
  )
}

/**
 * Which column a panel belongs in.
 *
 * The engine takes this as the opaque string it places panels by, so a source
 * type that brings its own view — a topic browser, a replication monitor, a
 * query editor — is a new kind with an existing role and needs no change to
 * the layout. Roles are three because the screen has three columns; a kind is
 * what a panel is, a role is where it goes, and the two stop matching one to
 * one as soon as the second kind of table exists. See the spec, T1.
 */
export const PANEL_ROLES = ["sources", "navigate", "work"] as const
export type PanelRole = (typeof PANEL_ROLES)[number]

export function roleOf(panel: Panel): PanelRole {
  switch (panel.kind) {
    case "connectors":
      return "sources"
    case "catalog":
      return "navigate"
    case "rows":
    case "structure":
    case "chart":
      return "work"
  }
}

/**
 * What a column shows before anything has been opened in it.
 *
 * Only the column of data has anything: the middle column with no catalog in
 * it is not a column yet, so it answers null and the engine leaves it off the
 * screen. The scene in the right-hand column carries the whole first run —
 * see P4 and P5.
 */
export function emptyOf(accepts: string | null): Component | null {
  switch (accepts) {
    case "work":
      return WorkspaceSceneView
    default:
      // "sources" and "navigate": the first is never empty, because its panel
      // cannot be closed, and the second appears together with a catalog.
      return null
  }
}

/**
 * What a panel leaves on screen when its column is pushed aside.
 *
 * Only the connections have anything to say at that width: which sources exist
 * and what the last check said, which is enough to open one of them again. A
 * catalog and a grid are lists of text and have nothing to show in forty
 * pixels, so they answer with nothing and the column is just a handle.
 */
export function collapsedOf(panel: Panel): Component | null {
  return panel.kind === "connectors" ? ConnectorRailView : null
}

export function lookOf(panel: Panel): PanelLook {
  switch (panel.kind) {
    case "connectors":
      // Not closable: it has no parameters, so a closed one leaves a column
      // with nothing to say about how to bring it back. See T3.
      return {
        title: "Connections",
        icon: "lan",
        closable: false,
        reloadTooltip: "Reload the list of connections",
      }
    case "catalog":
      return {
        title: panel.title,
        icon: adapterIcon(panel.adapterType),
        iconTooltip: "Edit connection",
        reloadTooltip: "Re-read this level",
      }
    case "rows":
      // The icon of the source rather than a generic grid: with several
      // catalogs open the right-hand column holds tabs from several
      // connections at once. Pressing it goes to the catalog of the
      // connection that owns the node — the one way there that exists
      // nowhere else, where editing the connection has two others.
      //
      // The name of the connection is in the tooltip rather than beside the
      // title: two `users` from two databases would otherwise be the same
      // tab, and the tooltip has to say something anyway.
      return {
        title: panel.title,
        icon: adapterIcon(panel.adapterType),
        iconTooltip: `${panel.connectorName} · Show in catalog`,
        reloadTooltip: "Re-read this table",
      }
    case "structure":
      return {
        title: panel.title,
        icon: "account_tree",
        iconTooltip: `${panel.connectorName} · Structure`,
        reloadTooltip: "Re-read the structure",
      }
    case "chart":
      return {
        title: `${panel.title} chart`,
        icon: "insert_chart",
        iconTooltip: `${panel.connectorName} · Chart`,
        reloadTooltip: "Re-read this chart page",
      }
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
      return boundComponent(panel.id, () =>
        h(CatalogPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          title: panel.title,
          adapterType: panel.adapterType,
        })
      )
    case "rows":
      return boundComponent(panel.id, () =>
        h(RowsPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
          connectorName: panel.connectorName,
          adapterType: panel.adapterType,
          describable: panel.describable === true,
        })
      )
    case "structure":
      return boundComponent(panel.id, () =>
        h(StructurePanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
        })
      )
    case "chart":
      return boundComponent(panel.id, () =>
        h(ChartPanelView, {
          panelId: panel.id,
          viewKey: panel.viewKey,
          connectorId: panel.connectorId,
          request: panel.request,
          columns: panel.columns,
        })
      )
  }
}
