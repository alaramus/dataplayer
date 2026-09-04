import { inject } from "vue"
import type { InjectionKey, Ref } from "vue"

import type {
  ConnectorPublic,
  FetchRequest,
  NodeRepresentation,
  NodeReplacement,
  ReferencedRows,
  RowsView,
} from "@/client"
import type { Filter } from "@/features/grid/types"

/**
 * What one panel may ask the workspace to open.
 *
 * Provided by the page: the engine renders a panel with no props of its own,
 * and a panel has no business reaching into the layout.
 */
export interface WorkspaceActions {
  /** The connection whose catalog is being looked at, of those that are open. */
  activeConnectorId: Readonly<Ref<string | null>>
  /**
   * Every connection that has a catalog open somewhere.
   *
   * Two states rather than one, now that catalogs are as many as were opened:
   * a row says whether it is open at all, and the active one says so fully.
   * See P7.
   */
  openConnectorIds: Readonly<Ref<ReadonlySet<string>>>
  openCatalog: (connector: ConnectorPublic) => void
  /**
   * Show the catalog of a connection and point at one node in it.
   *
   * Opening and coming forward are one thing: a panel is identified by what it
   * shows, so asking for a catalog that is already open brings its tab
   * forward. What is added here is the pointing.
   */
  revealInCatalog: (connectorId: string, nodeId: string, label: string) => void
  /**
   * The node a catalog has just been asked to point at, or nothing.
   *
   * A piece of state rather than a call into the panel: the panel may not have
   * mounted yet — it was opened a moment ago — and a call does not survive
   * that, while something to watch does.
   */
  revealTarget: Readonly<Ref<RevealTarget | null>>
  /**
   * Take the pointing meant for this connection, if the current one is.
   *
   * Taken rather than read: it is acted on once, and a target left behind
   * would point again at the next thing that made the panel re-render.
   */
  takeReveal: (connectorId: string) => RevealTarget | null
  openRows: (request: OpenRowsRequest) => void
  /**
   * Show another table in a tab that is already showing one.
   *
   * The sheets of a workbook: the tab keeps its place in the strip and its
   * title becomes the sheet's, because a second tab per sheet turns "look at
   * the other one" into housekeeping (D51). The whole request rather than a
   * new id, because the tab is now about a different node — what it can be
   * described as and what else it opens as are that node's, not the old
   * one's.
   */
  showInPlace: (panelId: string, request: OpenRowsRequest) => void
  /** Open the source's chosen representation with the matching viewer. */
  openRepresentation: (request: OpenRepresentationRequest) => void
  /** A one-shot fragment handed to a Markdown panel opened from another document. */
  documentTarget: Readonly<Ref<DocumentTarget | null>>
  takeDocumentTarget: (connectorId: string, nodeId: string) => DocumentTarget | null
  /**
   * Open what a foreign key points at, showing exactly the rows it names.
   *
   * The target arrived from the source: its node, as the catalog describes
   * it, and a predicate built against that node's own columns. Nothing here
   * composes either one, and nothing takes the id apart (D21).
   */
  followReference: (request: FollowReferenceCommand) => void
  /**
   * The predicate a tab has just been asked to show, or nothing.
   *
   * State to watch rather than a call into the panel, for the reason
   * `revealTarget` is: the tab may have been opened a moment ago and not be
   * mounted yet.
   */
  followTarget: Readonly<Ref<FollowTarget | null>>
  /** Take the predicate meant for this tab, if this is the tab it named. */
  takeFollow: (connectorId: string, nodeId: string) => FollowTarget | null
  /**
   * Open what a link named, with the query the sender was looking at.
   *
   * The same two steps as `followReference`, for the same reason: the tab may
   * already be open, so opening brings it forward and what it is to show is
   * left where the tab picks it up. See D60.
   */
  openShared: (request: OpenSharedRequest) => void
  /** The shared view a tab has just been asked to show, or nothing. */
  sharedTarget: Readonly<Ref<SharedTarget | null>>
  /** Take the shared view meant for this tab, if this is the tab it named. */
  takeShared: (connectorId: string, nodeId: string) => SharedTarget | null
  openStructure: (request: OpenStructureRequest) => void
  /**
   * Show what one node is: its facts, and what its format states (D75).
   *
   * A panel rather than a window, because it is a read of a source that can
   * fail, be re-read and be kept open beside the thing it describes.
   */
  openSummary: (request: OpenSummaryRequest) => void
  /**
   * Show the library of query documents, filtered to one connection.
   *
   * One panel however many connections are open: a query belongs to a person
   * rather than to a source, and which connections it lists is a filter
   * inside it rather than a panel each (D65). The command that opens it
   * belongs to the connection being read (D69), so the connection it was
   * opened from arrives as that filter; null leaves the library whole.
   */
  openQueries: (connectorId: string | null) => void
  /** The connection the library has just been asked to filter to, or nothing. */
  queriesTarget: Readonly<Ref<string | null>>
  /** Take that filter, once, the way every other panel target is taken. */
  takeQueriesTarget: () => string | null
  /** Open one console, or bring the tab already showing it forward. */
  openQueryDocument: (request: OpenQueryDocumentRequest) => void
  /**
   * Give one captured result a panel of its own.
   *
   * Two runs are two panels even when their SQL is equal: comparing them is
   * what the existing split and drag are for (D65).
   */
  openQueryResult: (request: { resultId: string; title: string }) => void
  /**
   * Put a document's new name on its tab.
   *
   * The panel carries the title because a layout restored from storage has to
   * label its tabs before anything has been read, exactly as a rows tab
   * carries the name of its node. Renaming therefore has to say so.
   */
  renameQueryDocument: (documentId: string, title: string | null) => void
  /** Close the tab of a document that has just gone to Trash. */
  closeQueryDocument: (documentId: string) => void
  openChart: (request: OpenChartRequest) => void
  replaceNode: (connectorId: string, replacement: NodeReplacement) => void
  /**
   * Show the window of one connection, or an empty one for a new connection.
   *
   * Owned by the page rather than by the panel that lists connections: that
   * panel is not rendered while its column is collapsed, and a window inside
   * it would go with it — which is exactly when the catalog needs to open one.
   */
  editConnector: (connectorId: string | null) => void
}

/** One node of one connection, to be pointed at once its catalog is showing. */
export interface RevealTarget {
  connectorId: string
  nodeId: string
  /**
   * What the node is called, which the catalog cannot work out on its own.
   *
   * The id is the source's own string and the catalog never takes one apart,
   * so a node that has been deleted since the tab was opened has no name left
   * anywhere else — and "it is gone" is worth saying with the name in it.
   */
  label: string
}

/**
 * What a data tab needs to be opened, which is what it is labelled by.
 *
 * The connection travels with the request rather than being looked up when the
 * tab is drawn: the tab has to name it after a reload too, before the list of
 * connections has been read. See P8.
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
   * The node whose children are the other tables this one is one of.
   *
   * A workbook, for a sheet: it opens as its first sheet and holds the rest,
   * so the tab that opened offers them rather than sending somebody back to
   * the catalog to walk into a file (D51).
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

/**
 * What a details tab needs, which is what a structure tab needs: one node, and
 * the connection that labels the tab before anything has been read (P8).
 */
export type OpenSummaryRequest = OpenStructureRequest

/** What a grid asks for when somebody presses the arrow in a keyed cell. */
export interface FollowReferenceCommand {
  connectorId: string
  connectorName: string
  adapterType: string
  target: ReferencedRows
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
 * One console, and what its tab says while nothing has been read.
 *
 * The title travels for the reason a rows tab carries the name of its node: a
 * layout restored from storage draws its tabs before the first request
 * finishes. A draft has no title, and the tab says so in its own words.
 */
export interface OpenQueryDocumentRequest {
  documentId: string
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

export const workspaceActionsKey: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(workspaceActionsKey)
  if (actions === undefined) throw new Error("A panel used outside the workspace page")
  return actions
}
