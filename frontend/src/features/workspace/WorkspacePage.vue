<script setup lang="ts">
import { computed, provide } from "vue"

import {
  catalogPanelId,
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

provide(workspaceActionsKey, {
  activeConnectorId,
  openCatalog: (connectorId: string, title: string) => {
    // replace: the middle column holds one catalog. Dropping this flag is all
    // that stands between here and two catalogs side by side — see T4.
    workspace.open(
      { id: catalogPanelId(connectorId), kind: "catalog", connectorId, title },
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
})
</script>

<template>
  <AppLayout fill>
    <WorkspaceRoot :context="workspace.context" />
  </AppLayout>
</template>
