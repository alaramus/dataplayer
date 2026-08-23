<script setup lang="ts">
import { computed, provide, ref } from "vue"

import type { ConnectorPublic } from "@/client"
import AdapterCatalogDialog from "@/features/connectors/AdapterCatalogDialog.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import {
  connectorWindow,
  connectorWindowId,
  draftWindowId,
} from "@/features/connectors/windows"
import { useConnectors } from "@/features/connectors/api"
import {
  catalogPanelId,
  collapsedOf,
  componentOf,
  emptyOf,
  lookOf,
  panelSchema,
  roleOf,
  rowsPanelId,
} from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"
import { workspaceActionsKey } from "@/features/workspace/state"
import { AppLayout, useConfirm } from "@/shared/ui"
import { useWindows, WindowHost } from "@/shared/windows"
import { makeLeaf, makeSplit, useWorkspace, WorkspaceRoot } from "@/shared/workspace"

/**
 * The workspace: connections, a catalog and the data of one node, side by side.
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
})

/**
 * Which connection the catalog is showing.
 *
 * Read off the panels rather than kept beside them: one catalog is open at a
 * time by T4, and a second record of which one could disagree with the first.
 */
const activeConnectorId = computed(
  () => workspace.panels.value.find((panel) => panel.kind === "catalog")?.connectorId ?? null
)

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
const confirm = useConfirm()

const unsaved = ref(new Set<string>())

const windows = useWindows({
  confirmClose: async (id) => {
    if (!unsaved.value.has(id)) return true
    return await confirm({
      title: "Discard changes?",
      message: "This connection has changes that were never applied.",
      confirmLabel: "Discard",
      danger: true,
    })
  },
})

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

provide(workspaceActionsKey, {
  activeConnectorId,
  openCatalog: (connector: ConnectorPublic) => {
    // replace: the middle column holds one catalog. Dropping this flag is all
    // that stands between here and two catalogs side by side — see T4.
    workspace.open(
      {
        id: catalogPanelId(connector.id),
        kind: "catalog",
        connectorId: connector.id,
        title: connector.name,
        adapterType: connector.adapter_type,
      },
      { replace: true }
    )
  },
  openRows: (connectorId: string, nodeId: string, title: string) => {
    workspace.open({
      id: rowsPanelId(connectorId, nodeId),
      kind: "rows",
      connectorId,
      nodeId,
      title,
    })
  },
  editConnector: (connectorId: string | null) => {
    // A new connection starts at the catalog, an existing one at its window.
    if (connectorId === null) {
      catalogOpen.value = true
      return
    }
    const found = (connectors.data.value?.data ?? []).find((row) => row.id === connectorId)
    if (found) openConnectorWindow(found, null)
  },
})
</script>

<template>
  <AppLayout fill>
    <WorkspaceRoot :context="workspace.context" />

    <AdapterCatalogDialog
      v-model="catalogOpen"
      @pick="pickAdapterType"
    />

    <WindowHost :context="windows.context" />
  </AppLayout>
</template>
