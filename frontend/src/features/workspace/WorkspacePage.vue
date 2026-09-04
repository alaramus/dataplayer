<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from "vue"

import { useRouter } from "vue-router"

import type { ConnectorPublic, NodeReplacement, ServiceTemplateInfo } from "@/client"
import { useCurrentUser } from "@/features/auth/api"
import AdapterCatalogDialog from "@/features/connectors/AdapterCatalogDialog.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import { connectorWindow, connectorWindowId, draftWindowId } from "@/features/connectors/windows"
import { useConnectors } from "@/features/connectors/api"
import { useConnectorHealth } from "@/features/connectors/health"
import ServiceCredentialsDialog from "@/features/services/ServiceCredentialsDialog.vue"
import StartServiceDialog from "@/features/services/StartServiceDialog.vue"
import { useRequestService, useServices } from "@/features/services/api"
import type { StartRequest } from "@/features/services/starts"
import { useServiceJobs } from "@/features/services/jobs"
import { moveChartSpec } from "@/features/charts/persist"
import { takeShareIntent } from "@/features/shares/intent"
import { useAccessRequestEvents, wordingOf } from "@/features/shares/requests"
import ShareDialog from "@/features/shares/ShareDialog.vue"
import { chartViewKey } from "@/features/charts/view"
import { activeCatalogPanel } from "@/features/workspace/activeCatalog"
import CommandBar from "@/features/workspace/CommandBar.vue"
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
  queryPanelId,
  resultPanelId,
  roleOf,
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
  OpenRepresentationRequest,
  OpenRowsRequest,
  OpenSharedRequest,
  OpenStructureRequest,
  OpenSummaryRequest,
  RevealTarget,
  SharedTarget,
} from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { AppButton, AppLayout, useConfirm, useToast } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import { makeLeaf, makeSplit, useWorkspace, WorkspaceRoot } from "@/shared/workspace"

/**
 * The workspace: connections, catalogs and node-specific work, side by side.
 *
 * Three columns that are always there, because each one is a role rather than
 * a place something was once dragged to: `accepts` puts a newly opened panel
 * in the right column, and `pinned` keeps that column when the last thing in
 * it is closed. Everything else is the user's — widths, which tabs are open,
 * and a data tab torn off into a section of its own. See the spec, T5.
 */
const workspace = useWorkspace<Panel>({
  storageKey: "dataplayer-workspace",
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
  look: lookOf,
  component: componentOf,
  empty: emptyOf,
  collapsed: collapsedOf,
  // A click on the icon of a tab does the thing that tab has no other way to
  // do, rather than activating it; the tab still activates on a click anywhere
  // else. From a catalog that is the connection itself; from rows or content it
  // is the catalog the node came from, which is reachable nowhere else while
  // editing a connection has two other ways in. See T5.
  onIconClick: (panel) => {
    if (panel.kind === "catalog") editConnector(panel.connectorId)
    if (panel.kind === "rows" || panel.kind === "content") {
      revealInCatalog(panel.connectorId, panel.nodeId, panel.title)
    }
  },
  // What re-reading means belongs to the panel, so the panel says how and this
  // only calls it. A tab restored from storage and never opened has never
  // mounted and registered nothing — showing it is what reads it, and that is
  // what the button does there.
  onReload: async (panel) => {
    if (!(await reloads.reload(panel.id))) workspace.context.activate(panel.id)
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
const activeConnectorId = computed(() => {
  const panelId = activeCatalogPanel(
    workspace.context.tree.value,
    workspace.context.focusedLeaf.value
  )
  const panel = workspace.panels.value.find((one) => one.id === panelId)
  return panel?.kind === "catalog" ? panel.connectorId : null
})

const openConnectors = computed(() => openConnectorIds(workspace.panels.value))

/**
 * The windows of connections, owned by the page.
 *
 * Both columns that open one — the list of sources and the head of the
 * catalog — can be collapsed, and a collapsed column renders nothing at all.
 * A window living inside one of them would vanish with it.
 *
 * Several are open at once on purpose: one connection is read while another
 * is filled in beside it, which is what a modal window forbids. What
 * modality would have given is replaced by asking before a window with
 * unsaved changes is closed. See the spec, O1.
 */
const connectors = useConnectors()
const router = useRouter()
// Only an administrator is offered the accounts screen. The routes behind it
// refuse anybody else anyway; this keeps a door out of sight that would not
// open (D34).
const me = useCurrentUser()
const windows = useWindowManager()
const confirm = useConfirm()

// Panels say how they are re-read; the tab strip presses the button. Provided
// here so that every panel of this screen registers into the same one.
const reloads = createReloadRegistry()
provideReloadRegistry(reloads)

// The same arrangement for the other direction: panels say when they may go.
const closings = createCloseRegistry()
provideCloseRegistry(closings)

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

// The state of every connection, pushed while this screen is open. Called
// here and nowhere else: the server probes only while somebody is watching,
// and the workspace is what "watching" means.
useConnectorHealth()
// The work the server owns, watched for as long as this page lives: an
// event says something moved, and the queries say what it is now (D81).
useServiceJobs()
const requestService = useRequestService()

/**
 * The connection whose access is being answered, if any.
 *
 * A request is answered where grants are given, so the notification leads into
 * that dialog rather than to an inbox screen of its own (D61). The dialog is
 * hosted here for the reason the connection windows are: the column it would
 * otherwise live in can be collapsed.
 */
const requestsFor = ref<string | null>(null)

useAccessRequestEvents({
  onAsked: (event) => {
    toast.offer(wordingOf(event), {
      label: "Open",
      onClick: () => {
        requestsFor.value = event.connector_id
      },
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

function openConnectorWindow(connector: ConnectorPublic | null, adapterType: string | null) {
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
    toast.info(`Starting ${payload.label}`)
  } catch (cause) {
    toast.error(messageOf(cause, "It could not be started"))
  }
}

function editConnector(connectorId: string | null) {
  // A new connection starts at the catalog, an existing one at its window.
  if (connectorId === null) {
    catalogOpen.value = true
    return
  }
  const found = (connectors.data.value?.data ?? []).find((row) => row.id === connectorId)
  if (found) openConnectorWindow(found, null)
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
  workspace.open({
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
  workspace.open({
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
    workspace.open({
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
      workspace.open({
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
    workspace.open({
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
    const node = request.target.node
    workspace.open({
      id: rowsPanelId(request.connectorId, node.id),
      kind: "rows",
      connectorId: request.connectorId,
      nodeId: node.id,
      title: node.name,
      connectorName: request.connectorName,
      adapterType: request.adapterType,
      describable: node.describable === true,
    })
    followTarget.value = {
      connectorId: request.connectorId,
      nodeId: node.id,
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
    workspace.open({
      id: structurePanelId(request.connectorId, request.nodeId),
      kind: "structure",
      ...request,
    })
  },
  openSummary: (request: OpenSummaryRequest) => {
    workspace.open({
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
    workspace.open({ id: QUERIES_PANEL_ID, kind: "queries" })
  },
  queriesTarget,
  takeQueriesTarget: () => {
    const target = queriesTarget.value
    queriesTarget.value = null
    return target
  },
  openQueryDocument: (request: OpenQueryDocumentRequest) => {
    workspace.open({
      id: queryPanelId(request.documentId),
      kind: "query",
      documentId: request.documentId,
      title: request.title,
      connectorName: request.connectorName,
    })
  },
  openQueryDraft: (request: OpenQueryDraftRequest) => {
    workspace.open({
      id: queryDraftPanelId(request.draftId),
      kind: "query",
      draftId: request.draftId,
      connectorId: request.connectorId,
      title: request.title,
      connectorName: request.connectorName,
    })
  },
  openQueryResult: (request: { resultId: string; title: string }) => {
    workspace.open({
      id: resultPanelId(request.resultId),
      kind: "result",
      resultId: request.resultId,
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
  renameQueryDocument: (documentId: string, title: string | null) => {
    const panel = workspace.panels.value.find(
      (candidate) => candidate.id === queryPanelId(documentId)
    )
    if (panel === undefined || panel.kind !== "query" || panel.title === title) return
    workspace.replace(panel.id, { ...panel, title })
  },
  closeQueryDocument: (documentId: string) => {
    workspace.context.close(queryPanelId(documentId))
  },
  openChart: (request: OpenChartRequest) => {
    const viewKey = chartViewKey(request.connectorId, request.request, request.columns)
    workspace.open({
      id: chartPanelId(viewKey),
      kind: "chart",
      viewKey,
      ...request,
    })
  },
  replaceNode,
  editConnector,
})
</script>

<template>
  <AppLayout fill>
    <template #actions>
      <AppButton
        v-if="me.data.value?.is_superuser"
        variant="quiet"
        size="sm"
        label="Admin"
        data-testid="open-users"
        @click="router.push({ name: 'admin' })"
      />
    </template>

    <template #status>
      <CommandBar />
    </template>

    <WorkspaceRoot :context="workspace.context" />

    <ShareDialog
      v-if="requestsFor !== null"
      :model-value="true"
      :connector-id="requestsFor"
      @update:model-value="requestsFor = null"
    />

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
