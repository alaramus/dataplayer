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
import QueriesPanelView from "@/features/queries/QueriesPanel.vue"
import QueryDocumentPanelView from "@/features/queries/QueryDocumentPanel.vue"
import QueryResultPanelView from "@/features/queries/ResultPanel.vue"
import CatalogPanelView from "@/features/workspace/panels/CatalogPanel.vue"
import ConnectorRailView from "@/features/workspace/panels/ConnectorRail.vue"
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
    nodes: z.array(z.object({ id: z.string().min(1).max(2048), label: z.string() }))
      .min(1).max(MAX_RELATIONS)
      .refine((nodes) => new Set(nodes.map((node) => node.id)).size === nodes.length, "Nodes must be distinct"),
  }),
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
  // The library of query documents. No parameters: which connection it lists
  // is a filter inside it, so there is one of these however many are open.
  z.object({ id: z.string(), kind: z.literal("queries") }),
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
export const QUERIES_PANEL_ID = "queries"
export const queryPanelId = (documentId: string) => `query:${documentId}`
/** A console nobody has asked to keep is named by the draft it holds. */
export const queryDraftPanelId = (draftId: string) => `query:draft:${draftId}`
export const resultPanelId = (resultId: string) => `result:${resultId}`

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
 * The PDF renderer is the same kind of cost as the document stack: nobody who
 * does not open a PDF downloads it.
 */
const PdfPanelView = defineAsyncComponent(
  () => import("@/features/content/PdfPanel.vue")
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
    case "catalog":
    case "queries":
      return "navigate"
    case "rows":
    case "content":
    case "structure":
    case "summary":
    case "record":
    case "chart":
    case "query":
    case "result":
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
 * What a tab of rows is drawn as.
 *
 * The preferred representation of the node when the catalog told the panel
 * what they were, because that is exactly what the catalog itself drew. A node
 * that declared none — every table of a database — keeps the icon of its
 * source, which is what tells two tabs of one name from two connections apart.
 */
function rowsIcon(panel: Extract<Panel, { kind: "rows" }>): string {
  const preferred = panel.representations?.[0]
  if (preferred === undefined) return adapterIcon(panel.adapterType)
  return REPRESENTATION_ICONS[preferred.kind] ?? adapterIcon(panel.adapterType)
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
        icon: "hub",
        iconTooltip: `${panel.nodes.length} tables · ${panel.connectorName}`,
        reloadTooltip: "Re-read these relationships",
      }
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
      // Drawn the way the catalog drew the node, when the node said how: a
      // file whose one view is a table is a grid in the list, and a tab of it
      // showing a folder is the same node saying two different things about
      // itself. A database table says nothing of the kind, and keeps the icon
      // of its source — with several catalogs open the right-hand column holds
      // tabs from several connections at once.
      //
      // The name of the connection is in the tooltip rather than beside the
      // title, because two `users` from two databases would otherwise be the
      // same tab. Hover text and nothing more: the way back to the node in the
      // catalog is a button in the panel's own row of commands (D112).
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
        icon: "account_tree",
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read the structure",
      }
    case "summary":
      return {
        title: panel.title,
        icon: "info",
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read these details",
      }
    case "record":
      return {
        title: `${panel.title} row`,
        icon: "table_rows",
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read this row",
      }
    case "chart":
      return {
        title: `${panel.title} chart`,
        icon: "insert_chart",
        iconTooltip: panel.connectorName,
        reloadTooltip: "Re-read this chart page",
      }
    case "queries":
      return {
        title: "Queries",
        icon: "manage_search",
        reloadTooltip: "Re-read your queries",
      }
    case "query":
      // A document with no name says so on its tab rather than showing an
      // empty one: a draft is the ordinary state of a console, not a fault.
      return {
        title: panel.title ?? "Untitled query",
        icon: "terminal",
        iconTooltip:
          panel.connectorName === null
            ? "This connection is no longer available"
            : panel.connectorName,
        reloadTooltip: "Re-read this query",
      }
    case "result":
      return {
        title: panel.title,
        icon: "table_view",
        iconTooltip: "A captured result",
        reloadTooltip: "Re-read this captured result",
      }
  }
}

/**
 * One bound component per panel, kept. Three traps, each a bug once:
 *
 * - Vue tells components apart by identity, so a wrapper built afresh is a new
 *   type every render and the panel is remounted — reloading the catalog and
 *   losing the page the grid was on.
 * - Keyed by the workspace's key and not the panel's id, because an id is
 *   renamed when a console becomes a document.
 * - A component and not a render function: a functional component has no
 *   instance, so <KeepAlive> would have nothing to keep.
 */
const bound = new Map<string, Component>()

function boundComponent(key: string, render: () => VNode): Component {
  const kept = bound.get(key)
  if (kept !== undefined) return kept
  const made = defineComponent({ name: `PanelBinding-${key}`, setup: () => render })
  bound.set(key, made)
  return made
}

export function componentOf(panel: Panel, key: string): Component {
  switch (panel.kind) {
    case "relationships":
      return boundComponent(key, () => h(RelationshipPanelView, {
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
      return boundComponent(key, () =>
        h(CatalogPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          title: panel.title,
          adapterType: panel.adapterType,
        })
      )
    case "rows":
      return boundComponent(key, () =>
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
        return boundComponent(key, () =>
          h(ImagePanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
          })
        )
      }
      if (representation === "audio" || representation === "video") {
        return boundComponent(key, () =>
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
        return boundComponent(key, () =>
          h(PdfPanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
          })
        )
      }
      if (representation === "markdown") {
        return boundComponent(key, () =>
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
        return boundComponent(key, () =>
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
      return boundComponent(key, () =>
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
      return boundComponent(key, () =>
        h(StructurePanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
        })
      )
    case "summary":
      return boundComponent(key, () =>
        h(SummaryPanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
          title: panel.title,
        })
      )
    case "record":
      return boundComponent(key, () =>
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
      return boundComponent(key, () =>
        h(ChartPanelView, {
          panelId: panel.id,
          viewKey: panel.viewKey,
          connectorId: panel.connectorId,
          request: panel.request,
          columns: panel.columns,
        })
      )
    case "queries":
      return boundComponent(key, () => h(QueriesPanelView, { panelId: panel.id }))
    case "result":
      return boundComponent(key, () =>
        h(QueryResultPanelView, {
          panelId: panel.id,
          resultId: panel.resultId,
          title: panel.title,
        })
      )
    case "query":
      return boundComponent(key, () =>
        h(QueryDocumentPanelView, {
          panelId: panel.id,
          documentId: panel.documentId,
          draftId: panel.draftId,
          connectorId: panel.connectorId,
          connectorName: panel.connectorName,
        })
      )
  }
}
