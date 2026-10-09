import { appIcons } from "@/shared/ui/icons"

import { defineAsyncComponent, defineComponent, h } from "vue"
import type { Component, VNode } from "vue"
import { z } from "zod"

import ChartPanelView from "@/features/charts/ChartPanel.vue"
import ContentPanelView from "@/features/content/ContentPanel.vue"
import ImagePanelView from "@/features/content/ImagePanel.vue"
import MediaPanelView from "@/features/content/MediaPanel.vue"
import SqlPanelView from "@/features/content/SqlPanel.vue"
import { REPRESENTATION_ICONS } from "@/features/catalog/nodes"
import { adapterIcon } from "@/features/connectors/adapters"
import { widgetSchema } from "@/features/dashboards/dashboardModel"
import QueryDocumentPanelView from "@/features/queries/QueryDocumentPanel.vue"
import QueryResultPanelView from "@/features/queries/ResultPanel.vue"
import CatalogPanelView from "@/features/workspace/panels/CatalogPanel.vue"
import ConnectorRailView from "@/features/workspace/panels/ConnectorRail.vue"
import ConnectorsHeadView from "@/features/workspace/panels/ConnectorsHead.vue"
import ConnectorsPanelView from "@/features/workspace/panels/ConnectorsPanel.vue"
import RowsPanelView from "@/features/workspace/panels/RowsPanel.vue"
import RecordPanelView from "@/features/workspace/panels/RecordPanel.vue"
import StructurePanelView from "@/features/workspace/panels/StructurePanel.vue"
import SummaryPanelView from "@/features/workspace/panels/SummaryPanel.vue"
import WorkspaceSceneView from "@/features/workspace/panels/WorkspaceScene.vue"
import type { PanelLook } from "@/shared/workspace"
import { MAX_RELATIONS } from "@/features/relationships/model"

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

/**
 * What a content panel may show, in one place.
 *
 * The schema validates against it, the panel id is typed by it and the icon
 * table is keyed by it, so a representation added to the source cannot arrive
 * here half-known.
 */
export const CONTENT_REPRESENTATIONS = [
  "text",
  "json",
  "jsonl",
  "image",
  "markdown",
  "audio",
  "video",
  "pdf",
  "sql",
] as const
export type ContentRepresentation = (typeof CONTENT_REPRESENTATIONS)[number]

export const panelSchema = z.discriminatedUnion("kind", [
  z.object({
    id: z.string(),
    kind: z.literal("relationships"),
    connectorId: z.string(),
    connectorName: z.string(),
    adapterType: z.string(),
    nodes: z.array(z.object({ id: z.string().min(1).max(2048), label: z.string(), holdsNodes: z.boolean().optional() }))
      .min(1).max(MAX_RELATIONS)
      .refine((nodes) => new Set(nodes.map((node) => node.id)).size === nodes.length, "Nodes must be distinct"),
  }),
  z.object({ id: z.string(), kind: z.literal("connectors") }),
  z.object({
    id: z.string(),
    kind: z.literal("catalog"),
    connectorId: z.string(),
    title: z.string(),
    startAt: z.string().optional(),
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
    // The node whose children are the other tables this one is one of: a
    // workbook, for one of its sheets. Optional for the same reason the
    // representations below are — a layout saved before it restores without
    // one, and gains it the next time the node is opened.
    containerId: z.string().optional(),
    // Optional because a layout saved before this field existed restores
    // without it, and gains it the next time the node is opened. Every way of
    // opening a tab carries them: the catalog, a shared link and a followed
    // reference all hand over the node as the source described it (D36).
    representations: z
      .array(
        z.object({
          kind: z.enum(["table", ...CONTENT_REPRESENTATIONS]),
          title: z.string().min(1),
        })
      )
      .optional(),
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
    kind: z.literal("summary"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
    connectorName: z.string(),
    adapterType: z.string(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("record"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
    connectorName: z.string(),
    adapterType: z.string(),
    // Whether the source will describe this relation, which is where the key
    // badges beside each column come from. A file says no and is still read.
    describable: z.boolean().optional(),
    // Which row, as a place in a page rather than as a handle (D111). Part of
    // the panel and not a message to it: a tab restored from storage has to
    // come back on the row it was left on, and a message is gone by then.
    //
    // Optional for the reason every field added to a stored panel is optional:
    // a layout written before it exists must still restore. A required one
    // fails the whole layout, and the workspace comes back empty — which is
    // what this file learned the hard way.
    request: fetchRequestSchema.optional(),
    index: z.number().int().min(0).optional(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("content"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
    connectorName: z.string(),
    adapterType: z.string(),
    representation: z.enum(CONTENT_REPRESENTATIONS),
    tableTitle: z.string().min(1).optional(),
    // What the source calls this document's other representation, so the
    // button says the source's words rather than this screen's.
    sourceTitle: z.string().min(1).optional(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("query"),
    // The document this console became, once somebody asked to keep it. Absent
    // until then: a console opens outside the library, and "Remember" is what
    // makes a document of it (D65).
    documentId: z.string().optional(),
    // What names the text of a console nobody has kept. Its body lives in this
    // browser tab's own storage under this id and nowhere else — never in the
    // layout, which is durable and would make a plaintext library of it (D63).
    draftId: z.string().optional(),
    // Which connection it is written against. Carried while there is no
    // document to read it from.
    connectorId: z.string().optional(),
    // What the tab says. Null while the document has no name of its own; the
    // panel carries it so a restored layout can label its tabs before
    // anything has been read (D65).
    title: z.string().nullable(),
    connectorName: z.string().nullable(),
  }),
  z.object({
    id: z.string(),
    kind: z.literal("result"),
    connectorId: z.string().optional(),
    // Into the process-local store of D64, which is why a restored layout may
    // find it gone: the panel says so rather than pretending to reload it.
    resultId: z.string(),
    title: z.string(),
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
  // A dashboard widget lifted out of its window (D155). The widget is carried
  // whole because the tab is the same kind of copy the window was: a snapshot
  // of the moment it was opened, and the layout is durable, so the copy is
  // validated on the way back like everything else stored.
  z.object({
    id: z.string(),
    kind: z.literal("widget"),
    dashboardId: z.string(),
    widget: widgetSchema,
    rangeSeconds: z.number(),
    refreshSeconds: z.number(),
  }),
  // What a service printed, read again whenever the tab is shown (D155). One
  // tab per service: the question "why did it not start" has one answer.
  z.object({
    id: z.string(),
    kind: z.literal("service-logs"),
    serviceId: z.string(),
    serviceName: z.string(),
  }),
  // The Search tab (D205). Nothing but its id: the words are handed to it when
  // it is opened and never written into a layout or a tab group, so a tab
  // restored from either comes back empty.
  z.object({ id: z.string(), kind: z.literal("search") }),
])

export type Panel = z.infer<typeof panelSchema>
export type PanelKind = Panel["kind"]

/**
 * Kinds a stored layout may still hold that are panels no longer: the query
 * library moved to the panel at the foot of the screen (D143). A layout or tab
 * group saved with one open drops that tab rather than being refused whole.
 */
const RETIRED_KINDS: ReadonlySet<unknown> = new Set(["queries"])

export function isRetiredPanel(panel: unknown): boolean {
  return typeof panel === "object" && panel !== null && RETIRED_KINDS.has((panel as { kind?: unknown }).kind)
}

/**
 * An ordinary panel is identified by what it shows. Catalog copies opt into
 * separate identities so each can keep a different location.
 *
 * Opening the same table twice then activates the tab that is already there
 * rather than putting a second copy of it beside the first.
 */
export const catalogPanelId = (connectorId: string) => `catalog:${connectorId}`
export const rowsPanelId = (connectorId: string, nodeId: string) => `rows:${connectorId}:${nodeId}`
export const contentPanelId = (
  connectorId: string,
  nodeId: string,
  representation: ContentRepresentation
) => `content:${connectorId}:${nodeId}:${representation}`
export const structurePanelId = (connectorId: string, nodeId: string) =>
  `structure:${connectorId}:${nodeId}`
export const summaryPanelId = (connectorId: string, nodeId: string) =>
  `summary:${connectorId}:${nodeId}`
/**
 * One row view per relation, and not one per row: which row it is showing is
 * something the panel is told, the way a tab is told which predicate to apply
 * (D36). A tab per row would fill the strip by reading a table.
 */
export const recordPanelId = (connectorId: string, nodeId: string) =>
  `record:${connectorId}:${nodeId}`
export const chartPanelId = (viewKey: string) => `chart:${viewKey}`
export const queryPanelId = (documentId: string) => `query:${documentId}`
/** A console nobody has asked to keep is named by the draft it holds. */
export const queryDraftPanelId = (draftId: string) => `query:draft:${draftId}`
export const resultPanelId = (resultId: string) => `result:${resultId}`
/**
 * A widget tab is a second copy rather than the window moved: the window's own
 * id is already taken by what is shown, and opening a tab from two windows of
 * one widget is two tabs, so the id carries a fresh suffix (D155).
 */
export const widgetPanelId = (dashboardId: string, widgetId: string, uid: string) =>
  `widget-tab:${dashboardId}:${widgetId}:${uid}`
export const serviceLogsPanelId = (serviceId: string) => `service-logs:${serviceId}`
/** One Search tab: searching again brings it forward with the new words. */
export const SEARCH_PANEL_ID = "search"

/**
 * The whole Markdown stack — parser, sanitiser, KaTeX — is loaded only when a
 * document is opened. Somebody who never opens one never downloads it.
 */
const MarkdownPanelView = defineAsyncComponent(
  () => import("@/features/content/markdown/MarkdownPanel.vue")
)

const RelationshipPanelView = defineAsyncComponent(
  () => import("@/features/relationships/RelationshipPanel.vue")
)

/**
 * A widget tab carries the charting stack the dashboard does; somebody who
 * never lifts a widget into a tab never downloads it.
 */
const WidgetPanelView = defineAsyncComponent(
  () => import("@/features/dashboards/WidgetPanel.vue")
)

const ServiceLogsPanelView = defineAsyncComponent(
  () => import("@/features/services/ServiceLogsPanel.vue")
)

/**
 * The PDF renderer is the same kind of cost as the document stack: nobody who
 * does not open a PDF downloads it.
 */
const PdfPanelView = defineAsyncComponent(
  () => import("@/features/content/PdfPanel.vue")
)

const SearchTabView = defineAsyncComponent(
  () => import("@/features/search/SearchTab.vue")
)

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
    // The Search tab beside the catalogs: what is opened from it goes to the
    // work column, and the list it was opened from stays in sight (D205).
    case "catalog":
    case "search":
      return "navigate"
    case "rows":
    case "content":
    case "structure":
    case "summary":
    case "record":
    case "chart":
    case "query":
    case "result":
    case "widget":
    case "service-logs":
    case "relationships":
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
 * What a whole column is called once it is off the screen.
 *
 * The role and not the tab inside it: a column is a part of the window rather
 * than a document, and a button on the bar whose word changed as the active
 * tab changed could not be aimed at twice. The connections have no name here
 * on purpose — that column narrows to a strip of its own icons instead of
 * leaving the screen, which is worth the forty pixels.
 */
export function sectionLook(accepts: string | null): { title: string; icon: string } | null {
  switch (accepts) {
    case "navigate":
      return { title: "Navigation", icon: appIcons.accountTree }
    case "work":
      return { title: "Data", icon: appIcons.tableChart }
    default:
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

/**
 * What the head of a column holding only this panel shows instead of its tab.
 *
 * Only the connections: their column takes nothing else, and the panel can be
 * neither closed nor carried, so its tab named the column and did nothing.
 * Every other kind shares a column and needs a tab to be picked by.
 */
export function headOf(panel: Panel): Component | null {
  return panel.kind === "connectors" ? ConnectorsHeadView : null
}

/**
 * What a tab of rows is drawn as.
 *
 * The preferred representation of the node when the catalog told the panel
 * what they were, because that is exactly what the catalog itself drew. A node
 * that declared none — every table of a database — is a table, so it gets the
 * table icon; the catalog draws such a node the same way. Which connection a
 * tab belongs to is said by the tooltip, not the icon.
 */
function rowsIcon(panel: Extract<Panel, { kind: "rows" }>): string {
  const preferred = panel.representations?.[0]
  if (preferred === undefined) return REPRESENTATION_ICONS.table
  return REPRESENTATION_ICONS[preferred.kind] ?? REPRESENTATION_ICONS.table
}

/**
 * The connection a panel shows, by the name it had when the panel opened. A
 * catalog carries no name of its own: its tab is titled by its connection.
 */
export function connectionNameOf(panel: Panel): string | null {
  if ("connectorName" in panel) return panel.connectorName || null
  return panel.kind === "catalog" ? panel.title || null : null
}

export function lookOf(
  panel: Panel,
  colors?: ReadonlyMap<string, string | null | undefined>
): PanelLook {
  const connectorId = "connectorId" in panel ? panel.connectorId : undefined
  return {
    ...baseLookOf(panel),
    color: connectorId === undefined ? null : colors?.get(connectorId) ?? null,
  }
}

function baseLookOf(panel: Panel): PanelLook {
  switch (panel.kind) {
    case "relationships":
      return {
        title: `Relationships · ${panel.connectorName}`,
        icon: appIcons.hub,
        iconTooltip: `${panel.nodes.length} tables · ${panel.connectorName}`,
        reloadTooltip: "Re-read these relationships",
      }
    case "connectors":
      // Not closable: it has no parameters, so a closed one leaves a column
      // with nothing to say about how to bring it back. See T3.
      return {
        title: "Connections",
        icon: appIcons.lan,
        closable: false,
        reloadTooltip: "Reload the list of connections",
      }
    case "catalog":
      // The one tab whose icon is still a button: the connection behind a
      // catalog is not a thing the catalog's own row of commands reaches.
      return {
        title: panel.title,
        icon: adapterIcon(panel.adapterType),
        iconTooltip: "Edit connection",
        iconCommand: true,
        reloadTooltip: "Re-read this level",
      }
    case "rows":
      // Drawn the way the catalog drew the node, where the node said how; a
      // plain table is drawn as a table, the way the catalog draws it too.
      //
      // The connection is in the tooltip because two `users` from two
      // databases would otherwise be the same tab. Hover text and nothing
      // more: the way back to the node is a button in the panel's row (D112).
      return {
        title: panel.title,
        icon: rowsIcon(panel),
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read this table",
      }
    case "content":
      return {
        title: panel.title,
        icon: REPRESENTATION_ICONS[panel.representation],
        iconTooltip: panel.connectorName,
        reloadTooltip:
          panel.representation === "sql" ? "Re-read this DDL" : "Re-read this file",
      }
    case "structure":
      return {
        title: panel.title,
        icon: appIcons.accountTree,
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read the structure",
      }
    case "summary":
      return {
        title: panel.title,
        icon: appIcons.info,
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read these details",
      }
    case "record":
      return {
        title: `${panel.title} row`,
        icon: appIcons.tableRows,
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read this row",
      }
    case "chart":
      return {
        title: `${panel.title} chart`,
        icon: appIcons.insertChart,
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read this chart page",
      }
    case "query":
      // A document with no name says so on its tab rather than showing an
      // empty one: a draft is the ordinary state of a console, not a fault.
      return {
        title: panel.title ?? "Untitled query",
        icon: appIcons.terminal,
        iconTooltip:
          panel.connectorName === null
            ? "This connection is no longer available"
            : panel.connectorName,
      }
    case "result":
      return {
        title: panel.title,
        icon: appIcons.tableView,
        iconTooltip: "A captured result",
        reloadTooltip: "Re-read this captured result",
      }
    case "widget":
      // Named as the window it was lifted from was: the widget's own title and
      // the dashboard icon (D155).
      return {
        title: panel.widget.title,
        icon: appIcons.dashboard,
        iconTooltip: "A widget lifted out of its dashboard",
        reloadTooltip: "Re-read these readings",
      }
    case "service-logs":
      return {
        title: `Output of ${panel.serviceName}`,
        icon: appIcons.notes,
        reloadTooltip: "Re-read what it printed",
      }
    case "search":
      return {
        title: "Search",
        icon: appIcons.search,
        reloadTooltip: "Search again",
      }
  }
}

type Bind = (key: string, render: () => VNode) => Component

/**
 * What draws each panel of one workspace: one bound component per panel,
 * kept. Four traps, each a bug once:
 *
 * - Vue tells components apart by identity, so a wrapper built afresh is a new
 *   type every render and the panel is remounted — reloading the catalog and
 *   losing the page the grid was on.
 * - Keyed by the workspace's key and not the panel's id, because an id is
 *   renamed when a console becomes a document.
 * - A component and not a render function: a functional component has no
 *   instance, so <KeepAlive> would have nothing to keep.
 * - One cache per mounted workspace, never one for the module. A workspace
 *   hands its keys out from `k1` again each time it is mounted — back from
 *   Preferences, say — and a cache that outlived it gave a panel the
 *   component bound to whichever panel held that key before: a table's tab
 *   showed a catalog, or a tab closed before leaving came back in another's.
 */
export function panelComponents(): (panel: Panel, key: string) => Component {
  const bound = new Map<string, Component>()
  const bind: Bind = (key, render) => {
    const kept = bound.get(key)
    if (kept !== undefined) return kept
    const made = defineComponent({ name: `PanelBinding-${key}`, setup: () => render })
    bound.set(key, made)
    return made
  }
  return (panel, key) => componentFor(panel, key, bind)
}

function componentFor(panel: Panel, key: string, bind: Bind): Component {
  switch (panel.kind) {
    case "relationships":
      return bind(key, () => h(RelationshipPanelView, {
        panelId: panel.id,
        connectorId: panel.connectorId,
        connectorName: panel.connectorName,
        adapterType: panel.adapterType,
        nodes: panel.nodes,
      }))
    case "connectors":
      return ConnectorsPanelView
    case "catalog":
      // The engine renders a panel with no props of its own, so what a panel
      // needs is bound here, where the panel is still a typed object.
      return bind(key, () =>
        h(CatalogPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          title: panel.title,
          startAt: panel.startAt,
          adapterType: panel.adapterType,
        })
      )
    case "rows":
      return bind(key, () =>
        h(RowsPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
          connectorName: panel.connectorName,
          adapterType: panel.adapterType,
          describable: panel.describable === true,
          representations: panel.representations,
          containerId: panel.containerId,
        })
      )
    case "content": {
      // Read once: a narrowing on a property does not survive into the closure.
      const representation = panel.representation
      if (representation === "image") {
        return bind(key, () =>
          h(ImagePanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
          })
        )
      }
      if (representation === "audio" || representation === "video") {
        return bind(key, () =>
          h(MediaPanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
            representation,
          })
        )
      }
      if (representation === "pdf") {
        return bind(key, () =>
          h(PdfPanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
          })
        )
      }
      if (representation === "markdown") {
        return bind(key, () =>
          h(MarkdownPanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
            connectorName: panel.connectorName,
            adapterType: panel.adapterType,
            sourceTitle: panel.sourceTitle,
          })
        )
      }
      if (representation === "sql") {
        return bind(key, () =>
          h(SqlPanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
            connectorName: panel.connectorName,
            adapterType: panel.adapterType,
            tableTitle: panel.tableTitle,
          })
        )
      }
      return bind(key, () =>
        h(ContentPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
          connectorName: panel.connectorName,
          adapterType: panel.adapterType,
          representation,
          tableTitle: panel.tableTitle,
        })
      )
    }
    case "structure":
      return bind(key, () =>
        h(StructurePanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
        })
      )
    case "summary":
      return bind(key, () =>
        h(SummaryPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
          connectorName: panel.connectorName,
          adapterType: panel.adapterType,
        })
      )
    case "record":
      return bind(key, () =>
        h(RecordPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
          connectorName: panel.connectorName,
          adapterType: panel.adapterType,
          describable: panel.describable === true,
          request: panel.request,
          index: panel.index,
        })
      )
    case "chart":
      return bind(key, () =>
        h(ChartPanelView, {
          panelId: panel.id,
          viewKey: panel.viewKey,
          connectorId: panel.connectorId,
          request: panel.request,
          columns: panel.columns,
        })
      )
    case "result":
      return bind(key, () =>
        h(QueryResultPanelView, {
          panelId: panel.id,
          resultId: panel.resultId,
          title: panel.title,
        })
      )
    case "query":
      return bind(key, () =>
        h(QueryDocumentPanelView, {
          panelId: panel.id,
          documentId: panel.documentId,
          draftId: panel.draftId,
          connectorId: panel.connectorId,
          connectorName: panel.connectorName,
        })
      )
    case "widget":
      return bind(key, () => h(WidgetPanelView, { panelId: panel.id, panel }))
    case "service-logs":
      return bind(key, () => h(ServiceLogsPanelView, { panelId: panel.id, panel }))
    case "search":
      return bind(key, () => h(SearchTabView, { panelId: panel.id }))
  }
}
