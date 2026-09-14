<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onMounted, provide, ref, watch } from "vue"

import type { ConnectorDraft, ConnectorPublic, NodeReplacement, ServiceTemplateInfo } from "@/client"
import AdapterCatalogDialog from "@/features/connectors/AdapterCatalogDialog.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import { connectorWindow, connectorWindowId, draftWindowId } from "@/features/connectors/windows"
import { connectorsKey, useConnectors } from "@/features/connectors/api"
import { useConnectorHealth } from "@/features/connectors/health"
import ServiceCredentialsDialog from "@/features/services/ServiceCredentialsDialog.vue"
import ServicesCommand from "@/features/services/ServicesCommand.vue"
import StartServiceDialog from "@/features/services/StartServiceDialog.vue"
import { useRequestService, useServices } from "@/features/services/api"
import type { StartRequest } from "@/features/services/starts"
import { useServiceJobs } from "@/features/services/jobs"
import { followedRows } from "@/features/grid/references"
import { moveChartSpec } from "@/features/charts/persist"
import { takeShareIntent } from "@/features/shares/intent"
import { waitingKey } from "@/features/shares/attention"
import { useAccessRequestEvents, wordingOf } from "@/features/shares/requests"
import { PERMISSIONS_PAGE } from "@/features/connectors/windowPages"
import { chartViewKey } from "@/features/charts/view"
import { relationshipPanelId } from "@/features/relationships/model"
import { activeCatalogPanel } from "@/features/workspace/activeCatalog"
import CommandBar from "@/features/workspace/CommandBar.vue"
import ActivityIndicator from "@/features/activity/ActivityIndicator.vue"
import AiWindow from "@/features/ai/AiWindow.vue"
import { rememberAiOpen, rememberedAiOpen } from "@/features/ai/state"
import DashboardsSpace from "@/features/dashboards/DashboardsSpace.vue"
import SpaceSwitch from "@/features/dashboards/SpaceSwitch.vue"
import WorkspaceGroups from "@/features/workspace/WorkspaceGroups.vue"
import {
  catalogPanelId,
  chartPanelId,
  collapsedOf,
  componentOf,
  contentPanelId,
  emptyOf,
  lookOf,
  openConnectorIds,
  panelSchema,
  QUERIES_PANEL_ID,
  queryDraftPanelId,
  sectionLook,
  queryPanelId,
  resultPanelId,
  roleOf,
  recordPanelId,
  rowsPanelId,
  structurePanelId,
  summaryPanelId,
} from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"
import { createCloseRegistry, provideCloseRegistry } from "@/features/workspace/closable"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"
import type {
  DocumentTarget,
  FollowReferenceCommand,
  FollowTarget,
  OpenChartRequest,
  OpenQueryDocumentRequest,
  OpenQueryDraftRequest,
  OpenRelationshipsRequest,
  OpenRepresentationRequest,
  OpenRecordRequest,
  OpenRowsRequest,
  OpenSharedRequest,
  OpenStructureRequest,
  OpenSummaryRequest,
  RevealTarget,
  SharedTarget,
} from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import { useServerLeaveGuard } from "@/shared/servers/leaving"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { useSpaceStore } from "@/stores/space"
import { AppIconButton, AppLayout, useConfirm, useToast } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import {
  makeLeaf,
  makeSplit,
  useWorkspace,
  WorkspaceDetachTarget,
  WorkspaceRoot,
  WorkspaceTaskbar,
} from "@/shared/workspace"

/**
 * The workspace: connections, catalogs and node-specific work, side by side.
 *
 * Three columns that are always there, because each one is a role rather than
 * a place something was once dragged to: `accepts` puts a newly opened panel
 * in the right column, and `pinned` keeps that column when the last thing in
 * it is closed. Everything else is the user's — widths, which tabs are open,
 * and a data tab torn off into a section of its own. See the spec, T5.
 */
const connectors = useConnectors()
const connectorColors = computed(() => new Map(
  (connectors.data.value?.data ?? []).map((connector) => [connector.id, connector.tab_color])
))
const workspace = useWorkspace<Panel>({
  storageKey: serverStorageKey("dataplayer-workspace"),
  panelSchema,
  defaults: () => ({
    tree: makeSplit(
      "root",
      "row",
      [
        makeLeaf("sources", ["connectors"], { accepts: "sources", pinned: true }),
        makeLeaf("navigate", [], { accepts: "navigate", pinned: true }),
        makeLeaf("work", [], { accepts: "work", pinned: true }),
      ],
      [20, 28, 52]
    ),
    panels: [{ id: "connectors", kind: "connectors" }],
  }),
  kindOf: roleOf,
  look: (panel) => lookOf(panel, connectorColors.value),
  component: componentOf,
  empty: emptyOf,
  collapsed: collapsedOf,
  sectionLook,
  // The one thing a tab's icon still does, and the only kind that offers it:
  // the connection behind a catalog is not reachable from the catalog's own
  // row of commands, while everything a panel offers about the node it shows
  // is (D112). A look without `iconCommand` is never drawn as a button, so
  // this list cannot grow a kind that presses and does nothing.
  onIconClick: (panel) => {
    if (panel.kind === "catalog") editConnector(panel.connectorId)
  },
  // A tab is a person's decision to close something; what that costs is the
  // panel's to say. A console holding an open transaction is the reason (D66).
  beforeClose: (panelId) => closings.mayClose(panelId),
})

/**
 * Which connection is being looked at, and which have a catalog open at all.
 *
 * Read off the layout rather than kept beside it: a second record of where the
 * user is could disagree with the tree, and the tree cannot disagree with
 * itself. See P7.
 */
/**
 * Data or Dashboards (D125). Anything opened into the data workspace brings it
 * back, or opening a table while the dashboards cover it would do nothing
 * anybody could see.
 */
const space = useSpaceStore()
const dashboardsShown = computed(() => space.current === "dashboards")

function openPanel(panel: Panel) {
  space.show("data")
  workspace.open(panel)
}

// The same rule for what reaches the layout by another way: a saved tab group
// restored from the header, a column brought back from the bar.
watch(
  () => [workspace.context.tree.value, workspace.panels.value.map((one) => one.id).join("\u0000")] as const,
  () => {
    if (dashboardsShown.value) space.show("data")
  }
)

const activeConnectorId = computed(() => {
  const floating = workspace.panels.value.find((one) => one.id === workspace.context.focusedDetached.value)
  if (floating?.kind === "catalog") return floating.connectorId
  const panelId = activeCatalogPanel(
    workspace.context.tree.value,
    workspace.context.focusedLeaf.value
  )
  const panel = workspace.panels.value.find((one) => one.id === panelId)
  return panel?.kind === "catalog" ? panel.connectorId : null
})

const openConnectors = computed(() => openConnectorIds(workspace.panels.value))

/**
 * The windows of connections, owned by the page: both columns that open one
 * can be collapsed, a collapsed column renders nothing, and a window living
 * inside one would vanish with it.
 *
 * Several are open at once on purpose — one connection read while another is
 * filled in beside it — which is what a modal window forbids (spec O1).
 */
const me = useCurrentUser()
const windows = useWindowManager()
const confirm = useConfirm()

const AI_WINDOW_ID = "application-agent"

function openAgent() {
  rememberAiOpen(true)
  windows.open({
    id: AI_WINDOW_ID,
    look: { title: "AI", icon: "auto_awesome" },
    size: { width: 960, height: 680 },
    minSize: { width: 520, height: 420 },
    autoFit: false,
    component: AiWindow,
    onClosed: () => rememberAiOpen(false),
  })
}

// Panels say how they are re-read, and the button that asks stands in the
// panel's own row of commands (D112). Provided here so that every panel of
// this screen registers into the same one.
const reloads = createReloadRegistry()
provideReloadRegistry(reloads)

// The same arrangement for the other direction: panels say when they may go.
const closings = createCloseRegistry()
provideCloseRegistry(closings)
useServerLeaveGuard(async () => {
  for (const panel of workspace.panels.value) {
    if (!(await closings.mayClose(panel.id))) return false
  }
  return true
})

/**
 * The node a catalog has just been asked to point at.
 *
 * Held here rather than handed to the panel: the panel may have been opened a
 * moment ago and not be mounted yet, and a call does not survive that.
 */
const revealTarget = ref<RevealTarget | null>(null)
const followTarget = ref<FollowTarget | null>(null)
const documentTarget = ref<DocumentTarget | null>(null)
const sharedTarget = ref<SharedTarget | null>(null)
const queriesTarget = ref<string | null>(null)
const toast = useToast()
const queryClient = useQueryClient()

// The state of every connection, pushed while this screen is open. Called
// here and nowhere else: the server probes only while somebody is watching,
// and the workspace is what "watching" means.
useConnectorHealth()
// The work the server owns, watched for as long as this page lives: an
// event says something moved, and the queries say what it is now (D81).
useServiceJobs()
const requestService = useRequestService()

/**
 * A request is answered where grants are given, so the notification leads to
 * the connection's own window, open on the page that holds both, rather than
 * to an inbox screen of its own (D61).
 */
function answerRequestsFor(connectorId: string) {
  editConnector(connectorId, PERMISSIONS_PAGE)
}

useAccessRequestEvents({
  onAsked: (event) => {
    toast.offer(wordingOf(event), {
      label: "Open",
      onClick: () => answerRequestsFor(event.connector_id),
    })
  },
  onAnswered: (event) => {
    // Nothing opens by itself: the person is working on something else, and a
    // tab appearing under their hands is not a courtesy.
    if (event.outcome === "approved") toast.success(wordingOf(event))
    else toast.info(wordingOf(event))
  },
})

const unsaved = ref(new Set<string>())

function markDirty(id: string, dirty: boolean) {
  const next = new Set(unsaved.value)
  if (dirty) next.add(id)
  else next.delete(id)
  unsaved.value = next
}

function forget(id: string) {
  markDirty(id, false)
  windows.close(id)
}

function openConnectorWindow(
  connector: ConnectorPublic | null,
  adapterType: string | null,
  startOn?: string,
  draft?: ConnectorDraft
) {
  const opened = connector ? connectorWindowId(connector.id) : draftWindowId()

  // Read at call time, never captured: saving a draft renames the window, and
  // a handler closing the id it was created with would close nothing — the
  // window would stay on screen over the column it was opened from.
  const handle = { id: opened }

  windows.open(
    connectorWindow({
      id: opened,
      connector,
      adapterType,
      startOn,
      draft,
      // A saved draft becomes the window of the connection it created, so a
      // second Apply updates rather than opening a duplicate. See O7.
      onCreated: (created) => {
        const renamed = connectorWindowId(created.id)
        markDirty(handle.id, false)
        windows.rename(handle.id, renamed, {
          title: created.name,
          icon: adapterIcon(created.adapter_type),
        })
        handle.id = renamed
      },
      onClose: () => forget(handle.id),
      // Back to the catalog. It closes without asking: Back is only offered
      // for a connection that was never saved, and Cancel beside it says the
      // same thing about the same values.
      onBack: () => {
        forget(handle.id)
        catalogOpen.value = true
      },
      onDirty: (dirty) => markDirty(handle.id, dirty),
      beforeClose: async () => {
        if (!unsaved.value.has(handle.id)) return true
        return await confirm({
          title: "Discard changes?",
          message: "This connection has changes that were never applied.",
          confirmLabel: "Discard",
          danger: true,
        })
      },
    })
  )
}

/**
 * Adding a connection starts at the catalog, which stays a modal dialog: it
 * is a choice to be made, not a place to work in. See the spec, K3.
 */
const catalogOpen = ref(false)

function pickAdapterType(adapterType: string) {
  catalogOpen.value = false
  openConnectorWindow(null, adapterType)
}

/**
 * Ask this server to start one, instead of filling a form about somebody
 * else's.
 *
 * The catalog closes and one question is asked — what to call it — because a
 * person who starts two databases needs to tell them apart. Nothing is waited
 * for after that: the answer is a job, and where it has got to is shown
 * beside the connections until it becomes one (D83).
 */
const startingTemplate = ref<ServiceTemplateInfo | null>(null)

function askToStart(template: ServiceTemplateInfo) {
  catalogOpen.value = false
  startingTemplate.value = template
}

/**
 * The service whose connection details are waiting to be shown, if any.
 *
 * Whichever way it was asked for: where a service listens is not something
 * anybody chose — the port is the runtime's answer, and the host is not the
 * one the connection holds — so the moment it becomes usable is the moment to
 * say so. Which service that is comes from the request; when it is ready
 * comes from the services query, because a job event says something moved and
 * the query says what it moved to (D81).
 */
const justStarted = ref<string | null>(null)
const revealing = ref<{ id: string; name: string } | null>(null)
const services = useServices()

watch(
  () => services.data.value,
  (rows) => {
    const waiting = justStarted.value
    if (waiting === null) return
    const ready = (rows ?? []).find(
      (row) => row.id === waiting && row.connector_id !== null
    )
    if (ready === undefined) return
    justStarted.value = null
    revealing.value = { id: ready.id, name: ready.connector_name }
  }
)

async function startService(payload: {
  templateKey: string
  start: StartRequest
  label: string
}) {
  try {
    const accepted = await requestService.mutateAsync({
      template_key: payload.templateKey,
      start: payload.start,
    })
    justStarted.value = accepted.service.id
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be started"))
  }
}

function editConnector(connectorId: string | null, startOn?: string) {
  // A new connection starts at the catalog, an existing one at its window.
  if (connectorId === null) {
    catalogOpen.value = true
    return
  }
  const found = (connectors.data.value?.data ?? []).find((row) => row.id === connectorId)
  if (found) {
    openConnectorWindow(found, null, startOn)
    return
  }
  // Asked for a connection that is not there any more — from the activity
  // sheet, whose copy of what is waiting was read before somebody deleted its
  // subject. Silence is what a dead button looks like, so it says what
  // happened and re-reads the two lists that were wrong.
  toast.info("That connection is no longer here")
  void queryClient.invalidateQueries({ queryKey: connectorsKey })
  void queryClient.invalidateQueries({ queryKey: waitingKey })
}

function openCatalog(connector: ConnectorPublic) {
  // A switched-off connection is not a source. Refused here rather than in
  // each place that shows one, because both the list and the strip end up
  // here — and the server refuses it too, so this only saves the round trip
  // and the empty panel.
  if (!connector.enabled) {
    toast.info(`${connector.name} is switched off`)
    return
  }
  // As many catalogs as were opened: a panel is identified by what it shows,
  // so pressing the same connection again brings its tab forward rather than
  // opening a second one. See P6.
  openPanel({
    id: catalogPanelId(connector.id),
    kind: "catalog",
    connectorId: connector.id,
    title: connector.name,
    adapterType: connector.adapter_type,
  })
}

/**
 * Show the catalog of a connection and point at one node in it.
 *
 * The connection is looked up rather than carried by the tab: whether it is
 * switched off is not something a tab opened an hour ago can know, and the
 * refusal has to be the same one as anywhere else.
 */
function revealInCatalog(connectorId: string, nodeId: string, label: string) {
  const connector = (connectors.data.value?.data ?? []).find((row) => row.id === connectorId)
  if (connector === undefined) return
  openCatalog(connector)
  if (!connector.enabled) return
  revealTarget.value = { connectorId, nodeId, label }
}

/**
 * Open what a link named: the catalog pointing at the node, and the tab.
 *
 * The tab is brought forward if it is already open, and the sent query is left
 * for it to pick up rather than pushed into it — the panel may not be mounted
 * yet, and a call does not survive that while a piece of state does. See D60.
 */
function openShared(request: OpenSharedRequest) {
  openCatalog(request.connector)
  if (request.connector.enabled) {
    revealTarget.value = {
      connectorId: request.connector.id,
      nodeId: request.nodeId,
      label: request.title,
    }
  }
  openPanel({
    id: rowsPanelId(request.connector.id, request.nodeId),
    kind: "rows",
    connectorId: request.connector.id,
    nodeId: request.nodeId,
    title: request.title,
    connectorName: request.connector.name,
    adapterType: request.connector.adapter_type,
    describable: request.describable,
    representations: request.representations,
  })
  sharedTarget.value = {
    connectorId: request.connector.id,
    nodeId: request.nodeId,
    view: request.view,
  }
}

// A link the landing screen has already resolved. Taken once, on the way in:
// the workspace is where tabs live, and the landing screen has none.
onMounted(() => {
  if (rememberedAiOpen()) openAgent()
  const intent = takeShareIntent()
  if (intent === null) return
  openShared({
    connector: intent.connector,
    nodeId: intent.nodeId,
    title: intent.title,
    describable: intent.describable,
    representations: intent.representations,
    view: intent.view,
  })
  toast.info(`Opened what ${intent.sharedBy} shared`)
})

function replaceNode(connectorId: string, replacement: NodeReplacement) {
  for (const panel of [...workspace.panels.value]) {
    if (panel.kind === "relationships" && panel.connectorId === connectorId) {
      if (panel.nodes.some((node) => node.id === replacement.old_node_id)) {
        const nodes = panel.nodes.map((node) => node.id === replacement.old_node_id
          ? { id: replacement.new_node_id, label: replacement.title } : node)
        workspace.replace(panel.id, { ...panel, id: relationshipPanelId(connectorId, nodes), nodes })
      }
      continue
    }
    if (
      (panel.kind !== "rows" &&
        panel.kind !== "content" &&
        panel.kind !== "structure" &&
        panel.kind !== "chart") ||
      panel.connectorId !== connectorId
    ) {
      continue
    }
    const panelNodeId = panel.kind === "chart" ? panel.request.node_id : panel.nodeId
    if (panelNodeId !== replacement.old_node_id) continue
    if (panel.kind === "rows") {
      workspace.replace(panel.id, {
        ...panel,
        id: rowsPanelId(connectorId, replacement.new_node_id),
        nodeId: replacement.new_node_id,
        title: replacement.title,
      })
      continue
    }
    if (panel.kind === "content") {
      workspace.replace(panel.id, {
        ...panel,
        id: contentPanelId(connectorId, replacement.new_node_id, panel.representation),
        nodeId: replacement.new_node_id,
        title: replacement.title,
      })
      continue
    }
    if (panel.kind === "structure") {
      workspace.replace(panel.id, {
        ...panel,
        id: structurePanelId(connectorId, replacement.new_node_id),
        nodeId: replacement.new_node_id,
        title: replacement.title,
      })
      continue
    }
    const request = { ...panel.request, node_id: replacement.new_node_id }
    const viewKey = chartViewKey(connectorId, request, panel.columns)
    moveChartSpec(panel.viewKey, viewKey)
    workspace.replace(panel.id, {
      ...panel,
      id: chartPanelId(viewKey),
      viewKey,
      title: replacement.title,
      request,
    })
  }
}

provide(workspaceActionsKey, {
  activeConnectorId,
  openConnectorIds: openConnectors,
  openCatalog,
  revealInCatalog,
  revealTarget,
  takeReveal: (connectorId: string) => {
    const target = revealTarget.value
    if (target === null || target.connectorId !== connectorId) return null
    revealTarget.value = null
    return target
  },
  openRows: (request: OpenRowsRequest) => {
    openPanel({
      id: rowsPanelId(request.connectorId, request.nodeId),
      kind: "rows",
      ...request,
    })
  },
  showInPlace: (panelId: string, request: OpenRowsRequest) => {
    workspace.replace(panelId, {
      id: rowsPanelId(request.connectorId, request.nodeId),
      kind: "rows",
      ...request,
    })
  },
  openRepresentation: (request: OpenRepresentationRequest) => {
    const preferred = request.representations[0]
    if (preferred === undefined) return
    if (preferred.kind === "markdown" && request.fragment) {
      // Set before opening: a newly mounted panel can take it immediately,
      // while an already mounted one observes the same piece of state.
      documentTarget.value = {
        connectorId: request.connectorId,
        nodeId: request.nodeId,
        fragment: request.fragment,
      }
    }
    if (preferred.kind === "table") {
      openPanel({
        id: rowsPanelId(request.connectorId, request.nodeId),
        kind: "rows",
        connectorId: request.connectorId,
        nodeId: request.nodeId,
        title: request.title,
        connectorName: request.connectorName,
        adapterType: request.adapterType,
        describable: request.describable,
        representations: request.representations,
        containerId: request.containerId,
      })
      return
    }
    const table = request.representations.find((representation) => representation.kind === "table")
    const source = request.representations.find(
      (representation) => representation.kind === "text" && preferred.kind !== "text"
    )
    openPanel({
      id: contentPanelId(request.connectorId, request.nodeId, preferred.kind),
      kind: "content",
      connectorId: request.connectorId,
      nodeId: request.nodeId,
      title: request.title,
      connectorName: request.connectorName,
      adapterType: request.adapterType,
      representation: preferred.kind,
      ...(table === undefined ? {} : { tableTitle: table.title }),
      ...(source === undefined ? {} : { sourceTitle: source.title }),
    })
  },
  documentTarget,
  takeDocumentTarget: (connectorId: string, nodeId: string) => {
    const target = documentTarget.value
    if (target === null || target.connectorId !== connectorId || target.nodeId !== nodeId) {
      return null
    }
    documentTarget.value = null
    return target
  },
  /**
   * Open the target of a reference and hand its tab the predicate.
   *
   * Two steps rather than one because the tab may already be open: opening it
   * brings it forward, and what it is to show is left where the tab picks it
   * up. The tab is the relation, as every rows tab is — following a key from
   * two different rows is the same table with a different question asked of
   * it, and the answer to the last one is what a tab shows.
   */
  followReference: (request: FollowReferenceCommand) => {
    const opened = followedRows(request.target, {
      connectorId: request.connectorId,
      connectorName: request.connectorName,
      adapterType: request.adapterType,
    })
    openPanel({
      id: rowsPanelId(opened.connectorId, opened.nodeId),
      kind: "rows",
      ...opened,
    })
    followTarget.value = {
      connectorId: opened.connectorId,
      nodeId: opened.nodeId,
      filters: request.target.filters,
    }
  },
  followTarget,
  takeFollow: (connectorId: string, nodeId: string) => {
    const target = followTarget.value
    if (target === null) return null
    if (target.connectorId !== connectorId || target.nodeId !== nodeId) return null
    followTarget.value = null
    return target
  },
  openShared,
  sharedTarget,
  takeShared: (connectorId: string, nodeId: string) => {
    const target = sharedTarget.value
    if (target === null) return null
    if (target.connectorId !== connectorId || target.nodeId !== nodeId) return null
    sharedTarget.value = null
    return target
  },
  openStructure: (request: OpenStructureRequest) => {
    openPanel({
      id: structurePanelId(request.connectorId, request.nodeId),
      kind: "structure",
      ...request,
    })
  },
  /**
   * Which row a row view is on is a field of the panel, so opening another one
   * rewrites the panel that is already there rather than sending it a message.
   * A message would be gone by the time a stored layout was restored, and the
   * tab would come back empty (D111).
   */
  openRecord: (request: OpenRecordRequest) => {
    const panel = {
      id: recordPanelId(request.connectorId, request.nodeId),
      kind: "record" as const,
      ...request,
    }
    if (workspace.panels.value.some((open) => open.id === panel.id)) {
      space.show("data")
      workspace.replace(panel.id, panel)
      workspace.context.activate(panel.id)
      return
    }
    openPanel(panel)
  },
  openRelationships: (request: OpenRelationshipsRequest) => {
    openPanel({ id: relationshipPanelId(request.connectorId, request.nodes), kind: "relationships", ...request })
  },
  openSummary: (request: OpenSummaryRequest) => {
    openPanel({
      id: summaryPanelId(request.connectorId, request.nodeId),
      kind: "summary",
      ...request,
    })
  },
  openQueries: (connectorId: string | null) => {
    // Set before opening, so a panel mounted by this very call can take it,
    // while one that was already open observes the same piece of state. The
    // reason is the one `revealTarget` has: a call does not survive a panel
    // that is not mounted yet.
    queriesTarget.value = connectorId
    openPanel({ id: QUERIES_PANEL_ID, kind: "queries" })
  },
  queriesTarget,
  takeQueriesTarget: () => {
    const target = queriesTarget.value
    queriesTarget.value = null
    return target
  },
  openQueryDocument: (request: OpenQueryDocumentRequest) => {
    openPanel({
      id: queryPanelId(request.documentId),
      kind: "query",
      documentId: request.documentId,
      connectorId: request.connectorId,
      title: request.title,
      connectorName: request.connectorName,
    })
  },
  openQueryDraft: (request: OpenQueryDraftRequest) => {
    openPanel({
      id: queryDraftPanelId(request.draftId),
      kind: "query",
      draftId: request.draftId,
      connectorId: request.connectorId,
      title: request.title,
      connectorName: request.connectorName,
    })
  },
  openQueryResult: (request: { resultId: string; title: string; connectorId?: string }) => {
    openPanel({
      id: resultPanelId(request.resultId),
      kind: "result",
      resultId: request.resultId,
      connectorId: request.connectorId,
      title: request.title,
    })
  },
  rememberedQuery: (
    panelId: string,
    kept: { documentId: string; title: string | null; connectorName: string | null }
  ) => {
    const panel = workspace.panels.value.find((one) => one.id === panelId)
    if (panel === undefined || panel.kind !== "query") return
    workspace.replace(panelId, {
      ...panel,
      id: queryPanelId(kept.documentId),
      documentId: kept.documentId,
      draftId: undefined,
      title: kept.title,
      connectorName: kept.connectorName,
    })
  },
  renameQueryDocument: (documentId: string, title: string | null, connectorId?: string | null) => {
    const panel = workspace.panels.value.find(
      (candidate) => candidate.id === queryPanelId(documentId)
    )
    if (panel === undefined || panel.kind !== "query") return
    const source = connectorId === undefined ? panel.connectorId : connectorId ?? undefined
    if (panel.title === title && panel.connectorId === source) return
    workspace.replace(panel.id, { ...panel, title, connectorId: source })
  },
  closeQueryDocument: (documentId: string) => {
    workspace.context.close(queryPanelId(documentId))
  },
  openChart: (request: OpenChartRequest) => {
    const viewKey = chartViewKey(request.connectorId, request.request, request.columns)
    openPanel({
      id: chartPanelId(viewKey),
      kind: "chart",
      viewKey,
      ...request,
    })
  },
  replaceNode,
  editConnector,
  createConnector: (draft: ConnectorDraft) => {
    openConnectorWindow(null, draft.adapter_type, undefined, draft)
  },
})
</script>

<template>
  <AppLayout fill>
    <template #actions>
      <AppIconButton
        icon="auto_awesome"
        tooltip="Open AI"
        data-testid="open-ai"
        @click="openAgent"
      />
    </template>
    <template #header-overlay>
      <WorkspaceDetachTarget :context="workspace.context" />
    </template>
    <template #workspace-tools>
      <WorkspaceGroups
        v-if="me.data.value"
        :key="me.data.value.id"
        :user-id="me.data.value.id"
        :workspace="workspace"
      />
    </template>
    <template #status>
      <SpaceSwitch />
      <ServicesCommand />
      <CommandBar />
      <!-- Beside the windows on the same bar: a column put aside and a window
           put aside are the same fact about the screen (D69). -->
      <WorkspaceTaskbar :context="workspace.context" />
    </template>
    <template #status-end>
      <ActivityIndicator
        @answer-access="answerRequestsFor"
        @open-connection="editConnector"
      />
    </template>

    <WorkspaceRoot
      :context="workspace.context"
      :covered="dashboardsShown"
    >
      <template #cover>
        <DashboardsSpace />
      </template>
    </WorkspaceRoot>

    <AdapterCatalogDialog
      v-model="catalogOpen"
      @pick="pickAdapterType"
      @start="askToStart"
    />

    <StartServiceDialog
      v-model:template="startingTemplate"
      @start="startService"
    />

    <!-- The one that hands the password over, because this is the screen
         that knows a service has just been made (D89). -->
    <ServiceCredentialsDialog
      v-model:service="revealing"
      reveal
    />
  </AppLayout>
</template>
