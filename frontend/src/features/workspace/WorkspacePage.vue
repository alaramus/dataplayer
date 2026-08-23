<script setup lang="ts">
import { computed, provide, ref } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorDialog from "@/features/connectors/ConnectorDialog.vue"
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
import { AppLayout } from "@/shared/ui"
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
 * The window of a connection, owned by the page.
 *
 * Both columns that open it — the list of sources and the head of the catalog
 * — can be collapsed, and a collapsed column renders nothing at all. A window
 * living in one of them would vanish with it.
 */
const connectors = useConnectors()
const dialogOpen = ref(false)
const editing = ref<ConnectorPublic | null>(null)

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
    editing.value =
      connectorId === null
        ? null
        : ((connectors.data.value?.data ?? []).find((row) => row.id === connectorId) ?? null)
    dialogOpen.value = true
  },
})
</script>

<template>
  <AppLayout fill>
    <WorkspaceRoot :context="workspace.context" />

    <ConnectorDialog
      v-model="dialogOpen"
      :connector="editing"
    />
  </AppLayout>
</template>
