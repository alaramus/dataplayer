import { inject } from "vue"
import type { InjectionKey, Ref } from "vue"

import type {
  ConnectorDraft,
  ConnectorPublic,
  FetchRequest,
  NodeRepresentation,
  NodeReplacement,
  ReferencedRows,
  RowsView,
} from "@/client"
import type { Filter } from "@/features/grid/types"
import type { RangeSeconds, RefreshSeconds, Widget } from "@/features/dashboards/dashboardModel"
import type { DiagramNodeRef } from "@/features/relationships/model"

/**
 * What one panel may ask the workspace to open.
 *
 * Provided by the page: the engine renders a panel with no props of its own,
 * and a panel has no business reaching into the layout.
 */
export interface WorkspaceActions {
  /** The first panel's temporary name filter, shared by its head and list. */
  connectorNameFilter: Ref<string>
  connectorFilterOpen: Ref<boolean>
  /** The connection whose catalog is being looked at, of those that are open. */
  activeConnectorId: Readonly<Ref<string | null>>
  /** Every connection that has a catalog open somewhere. */
  openConnectorIds: Readonly<Ref<ReadonlySet<string>>>
  openCatalog: (connector: ConnectorPublic) => void
  duplicateCatalog: (panelId: string, startAt: string | null) => void
  /**
   * Offer this catalog to a pair: it waits for a second, or completes the one
   * waiting (D167). Absent where the page makes no pairs.
   */
  pairCatalog?: (panelId: string) => void
  /** Open a new connection with defaults prepared by a source action. */
  createConnector: (draft: ConnectorDraft) => void
  /**
   * Show the catalog of a connection and point at one node in it. A panel is
   * identified by what it shows, so asking for one already open brings its tab
   * forward; the pointing is what this adds.
   */
  revealInCatalog: (connectorId: string, nodeId: string, label: string) => void
  /**
   * The node a catalog has just been asked to point at, or nothing.
   *
   * State to watch and not a call into the panel: the panel may have been
   * opened a moment ago and not be mounted yet, and a call does not survive
   * that. Every `…Target` below exists for this reason.
   */
  revealTarget: Readonly<Ref<RevealTarget | null>>
  /**
   * Taken rather than read: a target left behind would point again at the next
   * thing that made the panel re-render. Every `take…` below does the same.
   */
  takeReveal: (connectorId: string) => RevealTarget | null
  openRows: (request: OpenRowsRequest) => void
  /**
   * Show another table in a tab already showing one — the sheets of a workbook
   * (D51). The whole request and not a new id: the tab is now about a different
   * node, and what it can be described as is that node's. What it is *called*
   * stays the caller's, so a tab on a file keeps the file's name.
   */
  showInPlace: (panelId: string, request: OpenRowsRequest) => void
  /** Open the source's chosen representation with the matching viewer. */
  openRepresentation: (request: OpenRepresentationRequest) => void
  /**
   * A console just put into the library, in the tab it is already in. A panel
   * is named by what it holds, so this is a different panel keeping the same
   * place in the strip — the move switching a sheet makes (D51).
   */
  rememberedQuery: (
    panelId: string,
    kept: { documentId: string; title: string | null; connectorName: string | null }
  ) => void
  /** A one-shot fragment handed to a Markdown panel opened from another document. */
  documentTarget: Readonly<Ref<DocumentTarget | null>>
  takeDocumentTarget: (connectorId: string, nodeId: string) => DocumentTarget | null
  /**
   * Open what a foreign key points at. The target arrived from the source —
   * nothing here composes it and nothing takes the id apart (D21).
   */
  followReference: (request: FollowReferenceCommand) => void
  /** The predicate a tab has just been asked to show, or nothing. */
  followTarget: Readonly<Ref<FollowTarget | null>>
  /** Take the predicate meant for this tab, if this is the tab it named. */
  takeFollow: (connectorId: string, nodeId: string) => FollowTarget | null
  /** Open what a link named, with the query the sender was looking at (D60). */
  openShared: (request: OpenSharedRequest) => void
  /** The shared view a tab has just been asked to show, or nothing. */
  sharedTarget: Readonly<Ref<SharedTarget | null>>
  /** Take the shared view meant for this tab, if this is the tab it named. */
  takeShared: (connectorId: string, nodeId: string) => SharedTarget | null
  openStructure: (request: OpenStructureRequest) => void
  /**
   * One row of a relation, read downwards (D111). One panel per relation, with
   * the row written into it: a stored layout then restores the tab on the row
   * it was left on, which a message to a panel could not survive.
   */
  openRecord: (request: OpenRecordRequest) => void
  openRelationships: (request: OpenRelationshipsRequest) => void
  /**
   * What one node is: its facts, and what its format states (D75). A panel and
   * not a window, because it is a read that can fail and be re-read.
   */
  openSummary: (request: OpenSummaryRequest) => void
  /**
   * The library of query documents. One panel however many connections are
   * open, because a query belongs to a person rather than to a source (D65);
   * the connection it was opened from arrives as a filter, null for all.
   */
  openQueries: (connectorId: string | null) => void
  /** The connection the library has just been asked to filter to, or nothing. */
  queriesTarget: Readonly<Ref<string | null>>
  /** Take that filter, once, the way every other panel target is taken. */
  takeQueriesTarget: () => string | null
  /** Open one console, or bring the tab already showing it forward. */
  openQueryDocument: (request: OpenQueryDocumentRequest) => void
  /** Open a console on a connection without putting anything in the library. */
  openQueryDraft: (request: OpenQueryDraftRequest) => void
  /**
   * One captured result, one panel. Two runs are two panels even when their
   * SQL is equal: comparing them is what the split and drag are for (D65).
   */
  openQueryResult: (request: { resultId: string; title: string; connectorId?: string }) => void
  /**
   * Put a document's new name on its tab: the panel carries the title so a
   * restored layout can label tabs before anything is read. An explicit null
   * connector clears an identity whose connection has gone away.
   */
  renameQueryDocument: (documentId: string, title: string | null, connectorId?: string | null) => void
  /** Close the tab of a document that was deleted from the library. */
  closeQueryDocument: (documentId: string) => void
  openChart: (request: OpenChartRequest) => void
  /**
   * A dashboard widget as a workspace tab, lifted out of its floating window
   * (D155). The widget travels with the request: the tab is the window's
   * snapshot, not another read of the dashboard, so a widget changed or removed
   * since does not reach it.
   */
  openWidgetTab: (request: OpenWidgetTabRequest) => void
  /**
   * What a service printed, as a workspace tab rather than a window (D155).
   * One tab per service: opening it again brings the tab that is there forward.
   */
  openServiceLogsTab: (request: { serviceId: string; serviceName: string }) => void
  replaceNode: (connectorId: string, replacement: NodeReplacement) => void
  /**
   * Owned by the page and not by the panel that lists connections: that panel
   * is not rendered while its column is collapsed, and a window inside it
   * would go with it — which is exactly when the catalog needs to open one.
   */
  editConnector: (connectorId: string | null) => void
}

/** One node of one connection, to be pointed at once its catalog is showing. */
export interface RevealTarget {
  connectorId: string
  nodeId: string
  /**
   * What the node is called: the id is the source's own string and is never
   * taken apart, so a node deleted since the tab was opened has its name
   * nowhere else, and "it is gone" is worth saying with the name in it.
   */
  label: string
}

/**
 * What a data tab needs to be opened. The connection travels with the request
 * rather than being looked up when the tab is drawn: after a reload the tab
 * has to name it before the list of connections has been read.
 */
export interface OpenRowsRequest {
  connectorId: string
  nodeId: string
  /** The node, which is what the tab is called. */
  title: string
  /** Whose it is. In the tooltip of the tab rather than beside its title. */
  connectorName: string
  adapterType: string
  /** Whether this tabular node also has a relation model. */
  describable: boolean
  /**
   * What the node said it can be opened as, when the caller was told.
   *
   * Only so the tab is drawn the way the catalog drew the node. A caller that
   * does not have them — a table of a database is not a node with views —
   * leaves them out and the tab keeps the icon of its source.
   */
  representations?: NodeRepresentation[]
  /**
   * The node whose children are this one's sibling tables — a workbook, for a
   * sheet — so the tab offers them instead of sending somebody back to the
   * catalog to walk into a file (D51).
   */
  containerId?: string
}

export interface OpenRepresentationRequest {
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  representations: NodeRepresentation[]
  describable: boolean
  /** A heading id from a relative document link, not part of panel identity. */
  fragment?: string
  /** The node whose children are this one's sibling tables, when it has one. */
  containerId?: string
}

export interface DocumentTarget {
  connectorId: string
  nodeId: string
  fragment: string
}

export interface OpenStructureRequest {
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
}

export type OpenSummaryRequest = OpenStructureRequest

/** What a grid asks for when somebody presses the arrow in a keyed cell. */
export interface FollowReferenceCommand {
  connectorId: string
  connectorName: string
  adapterType: string
  target: ReferencedRows
}

/** What a grid asks for when somebody opens one of its rows. */
export interface OpenRecordRequest {
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  /** Whether the source will describe this relation; badges come from that. */
  describable: boolean
  /** The page the row is in, exactly as the grid asked for it. */
  request: FetchRequest
  /** Which row of that page, from zero. */
  index: number
}

/** One tab, and the predicate it is to show when it comes up. */
export interface FollowTarget {
  connectorId: string
  nodeId: string
  filters: Filter[]
}

/** A link that resolved to a node this caller may read. */
export interface OpenSharedRequest {
  connector: ConnectorPublic
  nodeId: string
  title: string
  describable: boolean
  representations: NodeRepresentation[]
  view: RowsView
}

/** One tab, and the shared view it is to show when it comes up. */
export interface SharedTarget {
  connectorId: string
  nodeId: string
  view: RowsView
}

/**
 * A console to open outside the library.
 *
 * The text is not in this request: whoever opens it writes it into the tab's
 * own storage under `draftId`, because the layout is durable and SQL in it
 * would be the plaintext browser cache D63 forbids.
 */
export interface OpenQueryDraftRequest {
  draftId: string
  connectorId: string
  connectorName: string | null
  /** What the tab is called before anybody has named the query. */
  title: string | null
}

export interface OpenQueryDocumentRequest {
  documentId: string
  connectorId?: string
  title: string | null
  connectorName: string | null
}

export interface OpenChartRequest {
  connectorId: string
  title: string
  connectorName: string
  adapterType: string
  request: FetchRequest
  columns: string[]
}

/** The copy of a widget a floating window held, to be kept as a tab (D155). */
export interface OpenWidgetTabRequest {
  dashboardId: string
  widget: Widget
  rangeSeconds: RangeSeconds
  refreshSeconds: RefreshSeconds
}

export interface OpenRelationshipsRequest {
  connectorId: string
  connectorName: string
  adapterType: string
  nodes: DiagramNodeRef[]
}

export const workspaceActionsKey: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(workspaceActionsKey)
  if (actions === undefined) throw new Error("A panel used outside the workspace page")
  return actions
}
