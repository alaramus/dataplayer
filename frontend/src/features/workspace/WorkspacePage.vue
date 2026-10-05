<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { useQueryClient } from "@tanstack/vue-query"
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, useTemplateRef, watch } from "vue"
import type { ShallowRef } from "vue"

import { ConnectorsService } from "@/client"
import type { ConnectorDraft, ConnectorPublic, NodeReplacement, ServiceTemplateInfo } from "@/client"
import AdapterCatalogDialog from "@/features/connectors/AdapterCatalogDialog.vue"
import ServerSwitcher from "@/features/servers/ServerSwitcher.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import { connectorWindow, connectorWindowId, draftWindowId } from "@/features/connectors/windows"
import { connectorsKey, useConnectors } from "@/features/connectors/api"
import { useConnectorHealth } from "@/features/connectors/health"
import ServiceCredentialsDialog from "@/features/services/ServiceCredentialsDialog.vue"
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
import { browserPlacesOf } from "@/features/search/browser"
import { offeredScope } from "@/features/search/context"
import { activeCatalogPanel } from "@/features/workspace/activeCatalog"
import { gainedPanels } from "@/features/workspace/gainedPanels"
import { searchFromOf } from "@/features/workspace/catalogSides"
import SearchField from "@/features/search/SearchField.vue"
import OnboardingDialog from "@/features/onboarding/OnboardingDialog.vue"
import { markVisited, shouldShowOnboarding } from "@/features/onboarding/onboarding"
import ActivityIndicator from "@/features/activity/ActivityIndicator.vue"
import AiSpace from "@/features/ai/AiSpace.vue"
import { screenContexts } from "@/features/ai/context"
import type { AiOpenIntent } from "@/features/ai/context"
import DashboardsSpace from "@/features/dashboards/DashboardsSpace.vue"
import PipelinesSpace from "@/features/pipelines/PipelinesSpace.vue"
import WorkspaceBottomPanel from "@/features/workspace/WorkspaceBottomPanel.vue"
import WorkspaceToolRail from "@/features/workspace/WorkspaceToolRail.vue"
import PairWaiting from "@/features/workspace/PairWaiting.vue"
import PairWindows from "@/features/workspace/PairWindows.vue"
import { usePairs } from "@/features/workspace/usePairs"
import { useTabGroups } from "@/features/workspace/useTabGroups"
import {
  catalogPanelId,
  chartPanelId,
  collapsedOf,
  contentPanelId,
  emptyOf,
  headOf,
  lookOf,
  openConnectorIds,
  panelComponents,
  isRetiredPanel,
  panelSchema,
  queryDraftPanelId,
  sectionLook,
  queryPanelId,
  resultPanelId,
  roleOf,
  recordPanelId,
  rowsPanelId,
  SEARCH_PANEL_ID,
  serviceLogsPanelId,
  structurePanelId,
  summaryPanelId,
  widgetPanelId,
} from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"
import { createCloseRegistry, provideCloseRegistry } from "@/features/workspace/closable"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { openIntentWith, workspaceActionsKey } from "@/features/workspace/state"
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
  OpenWidgetTabRequest,
  OpenHow,
  OpenIntent,
  RevealRequest,
  RevealTarget,
  SearchScope,
  SearchTarget,
  SharedTarget,
  WorkspaceActions,
} from "@/features/workspace/state"
import { messageOf, statusOf } from "@/shared/api/errors"
import { keysOf, keyshortcutsOf, onMac, registerShortcut } from "@/shared/keys/shortcuts"
import { serverStorageKey } from "@/shared/servers/context"
import { useServerLeaveGuard } from "@/shared/servers/leaving"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { useSpaceStore } from "@/stores/space"
import type { Space } from "@/stores/space"
import { AppFieldButton, AppIconButton, AppLayout, useConfirm, useToast } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import {
  leavesOf,
  makeLeaf,
  makeSplit,
  RAIL_MIN_PX,
  useWorkspace,
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
const connectorNameFilter = ref("")
const connectorFilterOpen = ref(false)
const connectorColors = computed(() => new Map(
  (connectors.data.value?.data ?? []).map((connector) => [connector.id, connector.tab_color])
))
const workspace = useWorkspace<Panel>({
  storageKey: serverStorageKey("dataplayer-workspace"),
  panelSchema,
  retired: isRetiredPanel,
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
  // Its own, because the keys it is handed start again on every mount.
  component: panelComponents(),
  empty: emptyOf,
  collapsed: collapsedOf,
  head: headOf,
  sectionLook,
  // The three columns of Data go no narrower than the Dashboards and AI rails,
  // so their heads keep their names at the same width.
  sectionMinWidth: (accepts) =>
    accepts === "sources" || accepts === "navigate" || accepts === "work" ? RAIL_MIN_PX : null,
  // The header button collapses the first column; its strip keeps no chevron
  // of its own.
  hideFirstCollapse: true,
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
 * Data, Dashboards or AI (D125, D141). Anything opened into the data workspace
 * brings it back, or opening a table while another space covers it would do
 * nothing anybody could see — except what the agent opens, which floats over
 * the space instead (`agentFloats`).
 */
const space = useSpaceStore()

/**
 * The header button collapses the first panel of the space being shown: the
 * leftmost data column, or the rail of the space covering the data. Each
 * space owns its collapsed state and exposes it through this one shape.
 *
 * The record names every space but Data, so a new one cannot arrive without
 * saying what its header button collapses; and each entry is the component's
 * own typed instance, so one that stops exposing the shape fails to compile.
 */
interface FirstPanelControl {
  toggleFirstPanel: () => void
  firstPanelCollapsed: boolean
}
const covers: Record<Exclude<Space, "data">, Readonly<ShallowRef<FirstPanelControl | null>>> = {
  dashboards: useTemplateRef<InstanceType<typeof DashboardsSpace>>("dashboards-cover"),
  ai: useTemplateRef<InstanceType<typeof AiSpace>>("ai-cover"),
  pipelines: useTemplateRef<InstanceType<typeof PipelinesSpace>>("pipelines-cover"),
}
const cover = computed(() => (space.current === "data" ? null : covers[space.current].value))
const firstDataLeaf = computed(() => leavesOf(workspace.context.tree.value)[0] ?? null)
const firstPanelCollapsed = computed(() =>
  space.current === "data"
    ? firstDataLeaf.value?.collapsed ?? false
    : cover.value?.firstPanelCollapsed ?? false
)
function toggleFirstPanel() {
  if (space.current !== "data") cover.value?.toggleFirstPanel()
  else if (firstDataLeaf.value !== null) workspace.context.toggleCollapse(firstDataLeaf.value.id)
}

/**
 * Where what is being opened goes, when it is opened from elsewhere: what the
 * agent or the search opens while another space is shown floats over that
 * space in a window of its own (D93, D141, D205) instead of calling Data
 * forward, and what the Search tab opens goes beside it. Set only for the
 * length of one `openWith` call, which opens synchronously.
 */
let routing: OpenHow | null = null
// Set while a panel is lifted into a window: opening it and lifting it out
// changes the layout, and that change must not call Data forward (below).
let lifting = false

function openPanel(panel: Panel) {
  if (routing?.float === true) {
    floatPanel(panel)
    return
  }
  space.show("data")
  workspace.open(panel, routing?.beside === undefined ? {} : { beside: routing.beside })
}

function openWith(how: OpenHow, open: () => void) {
  const before = routing
  routing = how
  try {
    open()
  } finally {
    routing = before
  }
}

/**
 * The panel in a window: opened and lifted out, or, already open in a column,
 * lifted out of it — docking it again puts it back where it was. A window
 * already holding it comes forward. One that cannot float is shown in Data.
 */
function floatPanel(panel: Panel) {
  const context = workspace.context
  if (context.detached.value.some((one) => one.panelId === panel.id)) {
    context.activate(panel.id)
    return
  }
  lifting = true
  workspace.open(panel)
  if (context.canDetach(panel.id)) context.detach(panel.id)
  else space.show("data")
  // Released after the watchers have run. Asked for before the layout
  // changed, the tick came ahead of them and they saw nothing set.
  void nextTick(() => { lifting = false })
}

// The same rule for what reaches the layout by another way: a saved tab group
// restored from the header, a column brought back from the bar. An arrival
// calls Data forward (gainedPanels); what only leaves — a window closed over
// another space — must not, or closing it takes the person to Data with
// nothing new to look at.
watch(
  () => [workspace.context.tree.value, workspace.panels.value.map((one) => one.id).join(" ")] as const,
  ([tree, ids], [previousTree, previousIds]) => {
    if (lifting || space.current === "data") return
    if (tree !== previousTree) {
      space.show("data")
      return
    }
    if (gainedPanels((previousIds ?? "").split(" ").filter(Boolean), ids.split(" ").filter(Boolean))) {
      space.show("data")
    }
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
const toast = useToast()
const queryClient = useQueryClient()

// One library of saved tab groups for the four rails. Each rail used to make
// its own, and a save button and a list standing on different rails then
// wrote their stale copies over each other. Made again only for another
// person, not for every refetch of the same one.
const meId = computed(() => me.data.value?.id ?? null)
const tabGroups = computed(() =>
  meId.value === null ? null : useTabGroups(meId.value, workspace, confirm, toast)
)

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
  // Nothing said here: the request is one entry in Needs you, which the event
  // has just refreshed, and its card is that entry arriving (D181). A message
  // of its own was a second record of the same request.
  onAsked: () => undefined,
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

/**
 * A connection by id. The browser holds the first page of the list — a
 * hundred — so one past it, found by the search or named by the agent, is
 * asked of the server, whose answer is the same 404 for gone and for not
 * this person's (D33).
 */
async function connectorOf(connectorId: string): Promise<ConnectorPublic | null> {
  const listed = (connectors.data.value?.data ?? []).find((row) => row.id === connectorId)
  if (listed !== undefined) return listed
  try {
    return (await ConnectorsService.readConnector({ path: { connector_id: connectorId } })).data
  } catch (cause) {
    if (statusOf(cause) === 404) return null
    throw cause
  }
}

/**
 * Said when a connection asked for is not there any more — from the activity
 * sheet, whose copy of what is waiting was read before somebody deleted its
 * subject, or from a search answered a moment ago. Silence is what a dead
 * button looks like, so it says what happened and re-reads the two lists that
 * were wrong.
 */
function connectionGone() {
  toast.info("That connection is no longer here")
  void queryClient.invalidateQueries({ queryKey: connectorsKey })
  void queryClient.invalidateQueries({ queryKey: waitingKey })
}

function editConnector(connectorId: string | null, startOn?: string) {
  // A new connection starts at the catalog, an existing one at its window.
  if (connectorId === null) {
    catalogOpen.value = true
    return
  }
  void (async () => {
    try {
      const found = await connectorOf(connectorId)
      if (found === null) connectionGone()
      else openConnectorWindow(found, null, startOn)
    } catch (cause) {
      toast.error(messageOf(cause, "Could not read that connection"))
    }
  })()
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
  // The ordinary catalog keeps one stable identity per connection. Copies
  // have their own ids, so pressing the connection still brings this one forward.
  openPanel({
    id: catalogPanelId(connector.id),
    kind: "catalog",
    connectorId: connector.id,
    title: connector.name,
    adapterType: connector.adapter_type,
  })
}

function duplicateCatalog(panelId: string, startAt: string | null, reveal?: RevealRequest) {
  const original = workspace.panels.value.find((panel) => panel.id === panelId)
  if (original?.kind !== "catalog") return
  // The connection's own catalog too busy to move asks another one already
  // open before making a third, which judges for itself by the same rule. Only
  // from the connection's own: two busy copies would hand it to each other.
  if (reveal !== undefined && panelId === catalogPanelId(original.connectorId)) {
    const other = [...workspace.panels.value].reverse().find(
      (panel) => panel.kind === "catalog" && panel.connectorId === original.connectorId && panel.id !== panelId
    )
    if (other !== undefined) {
      revealTarget.value = { ...reveal, connectorId: original.connectorId, panelId: other.id }
      // Over another space it floats, as what the search opens there does.
      if (space.current === "data") workspace.context.activate(other.id)
      else floatPanel(other)
      return
    }
  }
  const copyId = `${catalogPanelId(original.connectorId)}:copy:${crypto.randomUUID()}`
  const copy = { ...original, id: copyId, startAt: startAt ?? undefined }
  // Left before the copy exists, which takes it as it mounts.
  if (reveal !== undefined) revealTarget.value = { ...reveal, connectorId: original.connectorId, panelId: copyId }
  // A catalog in a window has no column to stand beside: its copy floats too,
  // as one made while another space is shown does.
  if (space.current !== "data" || workspace.context.detached.value.some((one) => one.panelId === panelId)) {
    floatPanel(copy)
    return
  }
  space.show("data")
  workspace.open(copy, { beside: panelId })

  // Splitting the catalog's old share in half would make both folders too
  // narrow to use. Give the pair room from the work column when they are all
  // siblings in the main row; the user can still resize every border.
  const layout = workspace.context.tree.value
  if (layout.kind !== "split" || layout.direction !== "row") return
  const indexOf = (id: string) => layout.children.findIndex(
    (child) => child.kind === "leaf" && child.panels.includes(id)
  )
  const sourceIndex = indexOf(panelId)
  const copyIndex = indexOf(copyId)
  const workIndex = layout.children.findIndex(
    (child) => child.kind === "leaf" && child.accepts === "work"
  )
  if (sourceIndex < 0 || copyIndex < 0 || workIndex < 0) return
  const sourceShare = layout.sizes[sourceIndex] ?? 0
  const copyShare = layout.sizes[copyIndex] ?? 0
  const workShare = layout.sizes[workIndex] ?? 0
  const extra = Math.max(0, Math.min(25 - sourceShare, 25 - copyShare, (workShare - 25) / 2))
  if (extra <= 0) return
  workspace.context.resize(layout.id, sourceIndex, workIndex, extra, 12)
  workspace.context.resize(layout.id, copyIndex, workIndex, extra, 12)
}

/**
 * Show the catalog of a connection and point at one node in it.
 *
 * The connection is looked up rather than carried by the tab: whether it is
 * switched off is not something a tab opened an hour ago can know, and the
 * refusal has to be the same one as anywhere else.
 */
function revealInCatalog(connectorId: string, nodeId: string, label: string) {
  void (async () => {
    try {
      const connector = await connectorOf(connectorId)
      if (connector === null) connectionGone()
      else revealIn(connector, { nodeId, label })
    } catch (cause) {
      toast.error(messageOf(cause, "Could not read that connection"))
    }
  })()
}

/**
 * The connection's own catalog, told where to point. Whether it can move there
 * without wiping a search, a filter or ticks is the catalog's to judge: only it
 * knows what it holds (D205).
 */
function revealIn(connector: ConnectorPublic, request: RevealRequest) {
  openCatalog(connector)
  if (!connector.enabled) return
  revealTarget.value = { ...request, connectorId: connector.id, panelId: catalogPanelId(connector.id) }
}

/**
 * Open what the agent or the search points at (D205): the connection is
 * looked up first, past the list's first page if it has to be, and what it
 * opens lands where `how` says.
 */
async function openIntent(intent: OpenIntent, how: OpenHow) {
  let connector: ConnectorPublic | null
  try {
    connector = await connectorOf(intent.connectorId)
  } catch (cause) {
    toast.error(messageOf(cause, "Could not read that connection"))
    return
  }
  if (connector === null) {
    connectionGone()
    return
  }
  const found = connector
  openWith(how, () => {
    openIntentWith({ ...actions, reveal: revealIn }, found, intent)
  })
}

/**
 * The Search tab, asked to search (D205). The words are left where the tab
 * picks them up, as every `…Target` here is: the tab may not be mounted yet.
 */
const searchTarget = ref<SearchTarget | null>(null)

function openSearch(target: SearchTarget, how: OpenHow) {
  searchTarget.value = target
  openWith(how, () => {
    openPanel({ id: SEARCH_PANEL_ID, kind: "search" })
  })
}

/**
 * A tab the search found among those open (S9): brought forward where it is.
 * A window floats over every space; a tab in a column is in Data.
 */
function openTab(panelId: string) {
  if (!workspace.panels.value.some((one) => one.id === panelId)) {
    toast.info("That tab is no longer open")
    return
  }
  if (!workspace.context.detached.value.some((one) => one.panelId === panelId)) space.show("data")
  workspace.context.activate(panelId)
}

/** A saved tab group the search found, restored as its own list restores it (D94). */
function openTabGroup(groupId: string) {
  const library = tabGroups.value
  const group = library?.groups.value.find((one) => one.id === groupId)
  if (library == null || group === undefined) {
    toast.info("That tab group is no longer saved")
    return
  }
  void library.open(group)
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
      panelId: catalogPanelId(request.connector.id),
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

/**
 * First-visit welcome. The visit is recorded on entry; the tour opens until
 * it was finished or skipped, then never again.
 */
const onboardingOpen = ref(false)
onMounted(() => {
  markVisited()
  if (shouldShowOnboarding()) onboardingOpen.value = true
})

// A link the landing screen has already resolved. Taken once, on the way in:
// the workspace is where tabs live, and the landing screen has none.
onMounted(() => {
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

/** Two catalogs of two connections in one window (D167). */
const pairs = usePairs(workspace, openCatalog)

const actions: WorkspaceActions = {
  connectorNameFilter,
  connectorFilterOpen,
  activeConnectorId,
  openConnectorIds: openConnectors,
  openCatalog,
  duplicateCatalog,
  pairCatalog: (panelId) => { pairs.offer(panelId) },
  pairCommandOf: (panelId) => pairs.commandOf(panelId),
  revealInCatalog,
  revealTarget,
  takeReveal: (connectorId: string, panelId: string) => {
    const target = revealTarget.value
    if (target === null || target.connectorId !== connectorId || target.panelId !== panelId) return null
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
  openWidgetTab: (request: OpenWidgetTabRequest) => {
    openPanel({
      id: widgetPanelId(request.dashboardId, request.widget.id, crypto.randomUUID()),
      kind: "widget",
      ...request,
    })
  },
  openServiceLogsTab: (request: { serviceId: string; serviceName: string }) => {
    openPanel({
      id: serviceLogsPanelId(request.serviceId),
      kind: "service-logs",
      ...request,
    })
  },
  replaceNode,
  editConnector,
  createConnector: (draft: ConnectorDraft) => {
    openConnectorWindow(null, draft.adapter_type, undefined, draft)
  },
  newConnection: pickAdapterType,
  connectorOf,
  openIntent,
  openWith,
  openSearch,
  searchTarget,
  takeSearch: () => {
    const target = searchTarget.value
    searchTarget.value = null
    return target
  },
  openTab,
  openTabGroup,
  browserPlaces: () => browserPlacesOf(workspace.panels.value, tabGroups.value?.groups.value ?? []),
}
provide(workspaceActionsKey, actions)

/**
 * What the agent asked to open, through the same ways in the catalog uses, so
 * the tab it opens is the tab the person would have got by hand — a document
 * with its table and source views, a sheet with its workbook. A copy of those
 * ways had already lost both. With the chat shown, it opens in a window over
 * the chat rather than in Data.
 */
function openFromAgent(intent: AiOpenIntent) {
  void openIntent(
    {
      connectorId: intent.connector_id,
      nodeId: intent.node_id,
      view: intent.view,
      title: intent.title,
      describable: intent.describable,
      representations: intent.representations,
    },
    { float: space.current !== "data" }
  )
}

/**
 * The search, opened over everything (D205): from the header and by Mod+K,
 * the application's first shortcut. A catalog that has the focus when it is
 * opened is offered as its scope, standing where the catalog stands; with the
 * focus anywhere else the tab being looked at names the scope when it can,
 * then the catalog being looked at, so closing the last table keeps the offer.
 */
const searchOpen = ref(false)
const searchField = useTemplateRef<InstanceType<typeof SearchField>>("search-field")
const searchOffer = ref<SearchScope | null>(null)
const connectorNames = computed(
  () => new Map((connectors.data.value?.data ?? []).map((connector) => [connector.id, connector.name] as const))
)
const scopeOffer = computed(() =>
  offeredScope(
    workspace.panels.value,
    workspace.context.tree.value,
    workspace.context.focusedLeaf.value,
    workspace.context.focusedDetached.value,
    searchFromOf,
    (connectorId) => connectorNames.value.get(connectorId) ?? null
  )
)

function openSearchField() {
  searchOffer.value = scopeOffer.value
  if (searchOpen.value) searchField.value?.show()
  else searchOpen.value = true
}

const searchKeys = keysOf("k", onMac())
const searchKeyshortcuts = keyshortcutsOf("k", onMac())
const unregisterSearch = registerShortcut({
  id: "search",
  key: "k",
  action: "Search everything",
  run: openSearchField,
})
onBeforeUnmount(unregisterSearch)
</script>

<template>
  <AppLayout fill>
    <template #header-start>
      <!-- On the axis of the left rail buttons below: a 36 px box pulled
           back over the toolbar padding, so the button stands where the
           rail's own buttons stand. -->
      <span class="workspace-header-collapse">
        <AppIconButton
          :icon="firstPanelCollapsed ? appIcons.panelOpen : appIcons.panelClose"
          :tooltip="firstPanelCollapsed ? 'Show first panel' : 'Hide first panel'"
          data-testid="app-toggle-first-panel"
          @click="toggleFirstPanel"
        />
      </span>
      <PairWaiting :pairs="pairs" />
    </template>
    <template #header-center>
      <AppFieldButton
        label="Search"
        :icon="appIcons.search"
        :keys="searchKeys"
        :keyshortcuts="searchKeyshortcuts"
        data-testid="search-button"
        @click="openSearchField"
      />
    </template>
    <template #status>
      <!-- The icon-only server at the very left edge, on the same axis as
           the left rail buttons. -->
      <span class="workspace-footer-server">
        <ServerSwitcher icon-only />
      </span>
      <!-- Beside the windows on the same bar: a column put aside and a window
           put aside are the same fact about the screen (D69). -->
      <WorkspaceTaskbar :context="workspace.context" />
    </template>
    <template #status-end>
      <!-- The bell on the axis of the right rail buttons above, mirroring the
           server icon on the left; what is running reads leftwards from it. -->
      <span class="workspace-footer-end">
        <ActivityIndicator
          @answer-access="answerRequestsFor"
          @open-connection="editConnector"
          @open-search="openSearch($event, { float: space.current !== 'data' })"
        />
      </span>
    </template>

    <!-- PyCharm-like side rails flank the sections — two equal halves a
         side, four rails. The blocks are icon-only and draggable within and
         across all of them. -->
    <div class="workspace-shell">
      <div class="workspace-shell__side">
        <WorkspaceToolRail
          v-if="tabGroups"
          zone="left-top"
          :groups="tabGroups"
        />
        <WorkspaceToolRail
          v-if="tabGroups"
          zone="left-bottom"
          :groups="tabGroups"
        />
      </div>
      <div class="workspace-shell__center">
        <div class="workspace-shell__spaces">
          <WorkspaceRoot
            :context="workspace.context"
            :covered="space.current !== 'data'"
          >
            <template #cover>
              <!-- Kept alive once shown: a window a space opened stays while
                   another is shown (D125), and the space is as it was left. -->
              <KeepAlive>
                <DashboardsSpace
                  v-if="space.current === 'dashboards'"
                  ref="dashboards-cover"
                />
                <AiSpace
                  v-else-if="space.current === 'ai'"
                  ref="ai-cover"
                  :contexts="screenContexts(workspace.panels.value)"
                  @open="openFromAgent"
                />
                <PipelinesSpace
                  v-else-if="space.current === 'pipelines'"
                  ref="pipelines-cover"
                />
              </KeepAlive>
            </template>
            <template #windows>
              <PairWindows :pairs="pairs" />
            </template>
          </WorkspaceRoot>
        </div>
        <!-- Under every space, not inside one: a tool at the foot of the
             screen stays where it is while the spaces change above it (D143). -->
        <WorkspaceBottomPanel />
      </div>
      <div class="workspace-shell__side">
        <WorkspaceToolRail
          v-if="tabGroups"
          zone="right-top"
          :groups="tabGroups"
        />
        <WorkspaceToolRail
          v-if="tabGroups"
          zone="right-bottom"
          :groups="tabGroups"
        />
      </div>
    </div>

    <OnboardingDialog v-model="onboardingOpen" />

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

    <SearchField
      ref="search-field"
      v-model:open="searchOpen"
      :offer="searchOffer"
    />
  </AppLayout>
</template>

<style scoped>
/* The rails are the side panels — the fill layout already goes edge to edge,
   so they stand flush against the window edges. */
.workspace-shell {
  display: flex;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
.workspace-shell__center {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.workspace-shell__spaces {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
/* One side column: its two rails split it into equal halves. */
.workspace-shell__side {
  flex: none;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
/* The server icon stands on the axis of the rail buttons below and of the
   header button above: a 36 px box pulled back over the status padding, the
   button centred in it whatever its own width is. */
.workspace-footer-server {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  margin-left: calc(-1 * var(--dp-space-2));
}
.workspace-footer-server :deep(.q-btn) {
  min-width: 32px;
  min-height: 32px;
}
.workspace-footer-server :deep(.q-btn .q-icon) {
  font-size: var(--dp-icon-md);
}
/* The header button stands on the axis of the left rail buttons below: a
   36 px box pulled back over the toolbar padding, the way the footer server
   icon keeps the rail's 2 px edge padding and 32 px button. */
.workspace-header-collapse {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  margin-left: calc(-1 * var(--dp-space-3));
}
.workspace-header-collapse :deep(.q-btn) {
  min-width: 32px;
  min-height: 32px;
}
/* The right end of the footer, on the same axis: pulled back over the status
   padding, with the 32 px bell 2 px off the edge as if centred in a 36 px box.
   A running step stands before it and takes whatever width it needs. */
.workspace-footer-end {
  display: flex;
  align-items: center;
  padding-right: var(--dp-space-half);
  margin-right: calc(-1 * var(--dp-space-2));
}
</style>
