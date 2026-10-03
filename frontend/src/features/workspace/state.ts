import { inject } from "vue"
import type { InjectionKey, Ref } from "vue"

import type {
  BrowserPlace,
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

import type { PairCommand } from "./pairs"

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
  /**
   * Another catalog of the same connection beside this one, at `startAt`.
   * With `reveal`, the copy points at that node once it stands there: what a
   * catalog too busy to be moved asks for instead of being wiped (D205).
   */
  duplicateCatalog: (panelId: string, startAt: string | null, reveal?: RevealRequest) => void
  /**
   * Offer this catalog to a pair: it waits for a second, or completes the one
   * waiting (D167). Absent where the page makes no pairs.
   */
  pairCatalog?: (panelId: string) => void
  /** What that command says for this catalog now, and whether it is refused. */
  pairCommandOf?: (panelId: string) => PairCommand
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
  takeReveal: (connectorId: string, panelId: string) => RevealTarget | null
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
  /** New connection, standing on one source type: the catalog's choice made already. */
  newConnection: (adapterType: string) => void
  /**
   * A connection by id: out of the browser's list, or asked of the server when
   * it is not on the list's first page. Null when it is gone or not the
   * person's to see.
   */
  connectorOf: (connectorId: string) => Promise<ConnectorPublic | null>
  /**
   * A connection or a node of one, opened from somewhere that only holds a
   * pointer to it — the agent, the search — through the same ways the catalog
   * opens it (D205). Says so when the connection is gone.
   */
  openIntent: (intent: OpenIntent, how: OpenHow) => Promise<void>
  /** Whatever `open` opens on this tick, opened the way `how` says. */
  openWith: (how: OpenHow, open: () => void) => void
  /**
   * The Search tab, asked to search (D205). One tab: opening it again brings
   * it forward with the new words.
   */
  openSearch: (target: SearchTarget, how: OpenHow) => void
  /** What the Search tab has just been asked to search, or nothing. */
  searchTarget: Readonly<Ref<SearchTarget | null>>
  takeSearch: () => SearchTarget | null
  /** An open tab or window, brought forward: what the search found it as. */
  openTab: (panelId: string) => void
  /** A saved tab group, restored after D94's warning. */
  openTabGroup: (groupId: string) => void
  /** The open tabs and saved tab groups, as the search is told of them (S9). */
  browserPlaces: () => BrowserPlace[]
}

/** The views a node opens in, as the agent's and the search's intents name them. */
export type NodeView = "catalog" | "preferred" | "rows" | "structure" | "summary"

/** A connection, or a node of one, named by a pointer to it. */
export interface OpenIntent {
  connectorId: string
  /** Absent for the connection itself, whose catalog opens. */
  nodeId?: string | null
  view: NodeView
  title?: string | null
  describable: boolean
  representations: NodeRepresentation[]
  /** The node whose children are this one's sibling tables, when it has one. */
  containerId?: string
  /** Where the node lives, as the pointer states it, for a catalog to be shown at. */
  ancestors?: readonly NodeAncestor[]
}

/**
 * One level above a node, as its source named it when the node was found: how
 * a catalog finds a node whose source has no node path — a Redis key (D205).
 */
export interface NodeAncestor {
  id: string
  label: string
}

/** Where something opened from elsewhere goes. */
export interface OpenHow {
  /**
   * Over the space being shown, in a window, rather than bringing Data
   * forward: what the agent and the search open while another space is shown
   * floats (D205).
   */
  float: boolean
  /**
   * A panel to keep in sight. A panel of its column opens in a section beside
   * it rather than as a tab over it: what the Search tab opens leaves the tab
   * on screen, as a catalog's does.
   */
  beside?: string
}

/** Where a search is limited to: one connection, from one level of it (D205). */
export interface SearchScope {
  connectorId: string
  /** What the connection is called, for the chip that shows the scope. */
  label: string
  /** The level the catalog stood on; null for the top of the connection. */
  nodeId: string | null
}

/**
 * What the Search tab is asked to search. Handed over once and never stored:
 * the tab keeps no words in the saved layout or a tab group (D205).
 */
export interface SearchTarget {
  words: string
  scope: SearchScope | null
}

/** A node to point at, in a catalog already chosen. */
export interface RevealRequest {
  nodeId: string
  /**
   * What the node is called: the id is the source's own string and is never
   * taken apart, so a node deleted since the tab was opened has its name
   * nowhere else, and "it is gone" is worth saying with the name in it.
   */
  label: string
  /** Where it lives, for a source that cannot say so itself (D205). */
  ancestors?: readonly NodeAncestor[]
}

/** One node of one connection, to be pointed at once its catalog is showing. */
export interface RevealTarget extends RevealRequest {
  connectorId: string
  /**
   * The catalog meant: the connection's own, or the copy opened for it. Two
   * catalogs of one connection would otherwise race for the target.
   */
  panelId: string
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

/** What an intent is opened through, its connection already in hand. */
export interface IntentOpeners
  extends Pick<WorkspaceActions, "openCatalog" | "openStructure" | "openSummary" | "openRepresentation" | "openRows"> {
  reveal: (connector: ConnectorPublic, request: RevealRequest) => void
}

/**
 * Turn an intent into a panel, through the actions that open each view, so
 * the tab is the one the person would have got from the catalog by hand.
 *
 * Synchronous on purpose: the caller has resolved the connection already, and
 * `openWith` holds where the panel lands only for the tick it is opened in.
 */
export function openIntentWith(actions: IntentOpeners, connector: ConnectorPublic, intent: OpenIntent): void {
  if (intent.nodeId == null) {
    actions.openCatalog(connector)
    return
  }
  const title = intent.title ?? intent.nodeId
  if (intent.view === "catalog") {
    actions.reveal(connector, {
      nodeId: intent.nodeId,
      label: title,
      ...(intent.ancestors === undefined ? {} : { ancestors: intent.ancestors }),
    })
    return
  }
  const node = {
    connectorId: connector.id,
    nodeId: intent.nodeId,
    title,
    connectorName: connector.name,
    adapterType: connector.adapter_type,
  }
  const described = {
    ...node,
    describable: intent.describable,
    representations: intent.representations,
    ...(intent.containerId === undefined ? {} : { containerId: intent.containerId }),
  }
  if (intent.view === "structure") actions.openStructure(node)
  else if (intent.view === "summary") actions.openSummary(node)
  else if (intent.view === "preferred" && intent.representations.length > 0) actions.openRepresentation(described)
  else actions.openRows(described)
}
