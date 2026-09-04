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
    // Retained only when the node was opened from a catalog that had just
    // declared its views. Old stored layouts and tabs opened by a reference
    // still restore without inventing alternatives.
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
      return {
        title: panel.title,
        icon: adapterIcon(panel.adapterType),
        iconTooltip: "Edit connection",
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
      // Pressing it goes to the catalog of the connection that owns the node,
      // which is the one way there that exists nowhere else; the name of the
      // connection is in the tooltip rather than beside the title, because two
      // `users` from two databases would otherwise be the same tab.
      return {
        title: panel.title,
        icon: rowsIcon(panel),
        iconTooltip: `${panel.connectorName} · Show in catalog`,
        reloadTooltip: "Re-read this table",
      }
    case "content":
      return {
        title: panel.title,
        icon: REPRESENTATION_ICONS[panel.representation],
        iconTooltip: `${panel.connectorName} · Show in catalog`,
        reloadTooltip:
          panel.representation === "sql" ? "Re-read this DDL" : "Re-read this file",
      }
    case "structure":
      return {
        title: panel.title,
        icon: "account_tree",
        iconTooltip: `${panel.connectorName} · Structure`,
        reloadTooltip: "Re-read the structure",
      }
    case "summary":
      return {
        title: panel.title,
        icon: "info",
        iconTooltip: `${panel.connectorName} · Details`,
        reloadTooltip: "Re-read these details",
      }
    case "chart":
      return {
        title: `${panel.title} chart`,
        icon: "insert_chart",
        iconTooltip: `${panel.connectorName} · Chart`,
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
 * instance, so <KeepAlive> in the workspace would have nothing to keep and a tab
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
    case "relationships":
      return boundComponent(panel.id, () => h(RelationshipPanelView, {
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
          representations: panel.representations,
          containerId: panel.containerId,
        })
      )
    case "content": {
      // Read once: a narrowing on a property does not survive into the closure.
      const representation = panel.representation
      if (representation === "image") {
        return boundComponent(panel.id, () =>
          h(ImagePanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
          })
        )
      }
      if (representation === "audio" || representation === "video") {
        return boundComponent(panel.id, () =>
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
        return boundComponent(panel.id, () =>
          h(PdfPanelView, {
            panelId: panel.id,
            connectorId: panel.connectorId,
            nodeId: panel.nodeId,
            title: panel.title,
          })
        )
      }
      if (representation === "markdown") {
        return boundComponent(panel.id, () =>
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
        return boundComponent(panel.id, () =>
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
      return boundComponent(panel.id, () =>
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
      return boundComponent(panel.id, () =>
        h(StructurePanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
        })
      )
    case "summary":
      return boundComponent(panel.id, () =>
        h(SummaryPanelView, {
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
    case "queries":
      return boundComponent(panel.id, () => h(QueriesPanelView, { panelId: panel.id }))
    case "result":
      return boundComponent(panel.id, () =>
        h(QueryResultPanelView, {
          panelId: panel.id,
          resultId: panel.resultId,
          title: panel.title,
        })
      )
    case "query":
      return boundComponent(panel.id, () =>
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
