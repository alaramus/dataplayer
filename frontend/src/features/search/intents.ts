import type { Hit } from "@/client"
import { toListNodes } from "@/features/catalog/nodes"
import type { NodeView, OpenHow, OpenIntent as NodeIntent } from "@/features/workspace/state"

/**
 * How a found thing opens: one client registry for every intent the server
 * can send (D205).
 *
 * A record over the generated union, so an intent the server adds fails to
 * compile here until somebody says what it opens. Each entry turns a hit into
 * a call to something that already opens that thing from its own list: a hit
 * is a pointer, and opening it is the workspace's business, not the search's.
 */
export type OpenIntent = Hit["open"]

/** What the registry calls. Each one exists somewhere already. */
export interface Openers {
  /**
   * A connection's catalog, or a node of one in a view — the agent's way in,
   * so a hit opens the tab a press in the catalog would have opened.
   */
  intent: (intent: NodeIntent, how: OpenHow) => void | Promise<void>
  /** A connection's own window, where a switched-off one is switched on. */
  connectionWindow: (connectorId: string) => void | Promise<void>
  /** The guide window, turned to a page. */
  guidePage: (key: string) => void
  /** New connection, standing on that type. */
  sourceType: (adapterType: string) => void
  savedQuery: (documentId: string, title: string, how: OpenHow) => void
  /** The Pipelines space, on that pipeline. */
  pipeline: (pipelineId: string) => void
  /** The Dashboards space, on that dashboard. */
  dashboard: (dashboardId: string) => void
  /** The AI space, on that conversation. */
  conversation: (conversationId: string) => void
  /** The quick chat's window, on that chat. */
  quickChat: (chatId: string) => void
  /** The AI space, that project's folder unfolded in its history. */
  project: (projectId: string) => void
  /** A service: the tool at the foot of the screen that lists them, on that row. */
  service: (serviceId: string) => void
  /** Preferences, on that key. */
  sshKey: (keyId: string) => void
  /** An open tab or window, brought forward. */
  tab: (panelId: string) => void
  /** A saved tab group, restored after its warning (D94). */
  tabGroup: (groupId: string) => void
  /** A hit whose target is not what its intent opens: said, never silent. */
  unopenable: (hit: Hit) => void
}

type Open = (hit: Hit, openers: Openers, how: OpenHow) => void | Promise<void>

/**
 * A node as an intent: what its listing said of it when live found it, and
 * only what the pointer says when it came from what was kept (D198). The
 * ancestors travel too, for a catalog whose source has no node path.
 */
export function nodeIntent(hit: Hit, view: NodeView): NodeIntent | null {
  if (hit.target.kind !== "node") return null
  const target = hit.target
  const listed = target.node === null ? undefined : toListNodes([target.node])[0]
  return {
    connectorId: target.connector_id,
    nodeId: target.node_id,
    view,
    title: target.name,
    describable: listed?.describable ?? false,
    representations: listed?.representations ?? [],
    ...(listed?.holdsNodes === true && listed.readable ? { containerId: target.node_id } : {}),
    ...(target.ancestors == null
      ? {}
      : { ancestors: target.ancestors.map((one) => ({ id: one.node_id, label: one.name })) }),
  }
}

function inView(view: NodeView): Open {
  return (hit, openers, how) => {
    const intent = nodeIntent(hit, view)
    return intent === null ? openers.unopenable(hit) : openers.intent(intent, how)
  }
}

/** An intent that opens one kind of application object by its id. */
function byId(type: string, open: (openers: Openers, id: string) => void): Open {
  return (hit, openers) => {
    if (hit.target.kind !== "object" || hit.target.object_type !== type) return openers.unopenable(hit)
    open(openers, hit.target.object_id)
  }
}

const inCatalog = inView("catalog")

export const INTENTS: Record<OpenIntent, Open> = {
  // A connection on its catalog; a node shown and marked in its catalog.
  catalog: (hit, openers, how) => {
    if (hit.target.kind === "connection") {
      return openers.intent(
        { connectorId: hit.target.connector_id, view: "catalog", describable: false, representations: [] },
        how
      )
    }
    return inCatalog(hit, openers, how)
  },
  preferred: inView("preferred"),
  rows: inView("rows"),
  structure: inView("structure"),
  summary: inView("summary"),
  connection: (hit, openers) => {
    if (hit.target.kind !== "connection") return openers.unopenable(hit)
    return openers.connectionWindow(hit.target.connector_id)
  },
  guide_page: byId("guide_page", (openers, key) => { openers.guidePage(key) }),
  source_type: byId("source_type", (openers, type) => { openers.sourceType(type) }),
  saved_query: (hit, openers, how) => {
    if (hit.target.kind !== "object" || hit.target.object_type !== "saved_query") return openers.unopenable(hit)
    return openers.savedQuery(hit.target.object_id, hit.title, how)
  },
  pipeline: byId("pipeline", (openers, id) => { openers.pipeline(id) }),
  dashboard: byId("dashboard", (openers, id) => { openers.dashboard(id) }),
  conversation: byId("conversation", (openers, id) => { openers.conversation(id) }),
  quick_chat: byId("quick_chat", (openers, id) => { openers.quickChat(id) }),
  project: byId("project", (openers, id) => { openers.project(id) }),
  service: byId("service", (openers, id) => { openers.service(id) }),
  ssh_key: byId("ssh_key", (openers, id) => { openers.sshKey(id) }),
  // Places only the browser knows: an open tab by its panel, a saved group by its id.
  tab: byId("tab", (openers, id) => { openers.tab(id) }),
  tab_group: byId("tab_group", (openers, id) => { openers.tabGroup(id) }),
}

/** Open a hit the way its own list would. */
export function openHit(hit: Hit, openers: Openers, how: OpenHow): void | Promise<void> {
  return INTENTS[hit.open](hit, openers, how)
}

/** Whether a hit can be shown in its catalog: every node can (D205). */
export function showsInCatalog(hit: Hit): boolean {
  return hit.target.kind === "node"
}

/**
 * Show in catalog, whatever the hit opens as: D112's gesture, in the
 * connection's own catalog, or another one when that one is busy (D205).
 */
export function showInCatalog(hit: Hit, openers: Openers, how: OpenHow): void | Promise<void> {
  return inCatalog(hit, openers, how)
}
