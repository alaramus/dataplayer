<script setup lang="ts">
import { provide } from "vue"

import {
  catalogPanelId,
  componentOf,
  kindOf,
  lookOf,
  panelSchema,
  rowsPanelId,
} from "@/features/workspace/panels"
import type { Panel } from "@/features/workspace/panels"
import { workspaceActionsKey } from "@/features/workspace/state"
import { AppLayout } from "@/shared/ui"
import { makeLeaf, useWorkspace, WorkspaceRoot } from "@/shared/workspace"

/**
 * The workspace: connections, a catalog and the data of one node, side by side.
 *
 * The layout is the user's own from the second visit onwards; the default is
 * only what the first one looks like — and it is a single section, because a
 * catalog panel names a connection the user has not chosen yet. Sections
 * appear as the work goes on: opening a catalog finds no section holding that
 * kind, so it lands beside the connections, and dragging a tab to an edge is
 * what splits them.
 */
const workspace = useWorkspace<Panel>({
  storageKey: "dataplayer-workspace",
  panelSchema,
  defaults: () => ({
    tree: makeLeaf("connections", ["connectors"]),
    panels: [{ id: "connectors", kind: "connectors" }],
  }),
  kindOf,
  look: lookOf,
  component: componentOf,
})

provide(workspaceActionsKey, {
  openCatalog: (connectorId: string, title: string) => {
    workspace.open({ id: catalogPanelId(connectorId), kind: "catalog", connectorId, title })
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
})
</script>

<template>
  <AppLayout fill>
    <WorkspaceRoot :context="workspace.context" />
  </AppLayout>
</template>
