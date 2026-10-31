<script setup lang="ts">
import { computed } from "vue"

import type { ContentRequest } from "@/client"
import JsonTreeNode from "@/features/content/JsonTreeNode.vue"
import { useContent } from "@/features/content/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppButton, AppSpinner, appIcons } from "@/shared/ui"

/**
 * A source's own description of a node, drawn as a JSON tree (D295).
 *
 * Read only: what a MongoDB collection's options, validator and indexes are,
 * the pipeline a report runs, or a znode's data (D298). A file's JSON is its
 * text, and opens in the editor instead. Where the node also opens as text or
 * as rows, the source's titles for those are given, and each is a button.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName?: string
  adapterType?: string
  sourceTitle?: string
  tableTitle?: string
}>()

const workspace = useWorkspaceActions()

function showSource() {
  if (props.sourceTitle === undefined) return
  workspace.openRepresentation({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName ?? "",
    adapterType: props.adapterType ?? "",
    representations: [
      { kind: "text", title: props.sourceTitle },
      ...(props.tableTitle === undefined ? [] : [{ kind: "table" as const, title: props.tableTitle }]),
    ],
    describable: false,
  })
}

function showTable() {
  if (props.tableTitle === undefined) return
  workspace.openRows({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName ?? "",
    adapterType: props.adapterType ?? "",
    describable: false,
    representations: [
      { kind: "table", title: props.tableTitle },
      ...(props.sourceTitle === undefined ? [] : [{ kind: "text" as const, title: props.sourceTitle }]),
    ],
  })
}

const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({ node_id: props.nodeId, representation: "tree" }))
const content = useContent(connectorId, request)
const errorKind = computed(() => errorKindOf(content.error.value))
const tree = computed(() => {
  const value = content.data.value
  return value?.kind === "json" ? (value.value ?? null) : null
})
const error = computed(() =>
  content.isError.value ? messageOf(content.error.value, t("content.tree.could_not_open")) : ""
)

useReloadable(() => props.panelId, async () => {
  await content.refetch()
})
</script>

<template>
  <div class="tree-panel">
    <div class="tree-panel__head">
      <!-- What is drawn, as the text editor names its own: a tree is a
           source's definition for MongoDB and a znode's data for ZooKeeper
           (D298), and JSON is true of both. -->
      <span class="tree-panel__kind">{{ t("content.tree.heading") }}</span>
      <!-- One block, so the head puts it at the end as the other panels do;
           the commands are several elements, each a flex item of their own. -->
      <div class="tree-panel__commands">
        <AppButton
          v-if="sourceTitle"
          variant="quiet"
          size="sm"
          :icon="appIcons.code"
          :label="sourceTitle"
          layout="toolbar"
          data-testid="tree-view-source"
          @click="showSource"
        />
        <AppButton
          v-if="tableTitle"
          variant="quiet"
          size="sm"
          :icon="appIcons.gridOn"
          :label="tableTitle"
          layout="toolbar"
          data-testid="tree-view-table"
          @click="showTable"
        />
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
        />
      </div>
    </div>
    <SourceErrorBanner
      v-if="error"
      :connector-id="connectorId"
      :error-kind="errorKind"
      data-testid="tree-error"
    >
      {{ error }}
    </SourceErrorBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <div
      v-else-if="tree !== null"
      class="tree-panel__body"
      data-testid="tree-body"
    >
      <JsonTreeNode
        :value="tree"
        :open-levels="1"
        root
      />
    </div>
  </div>
</template>

<style scoped>
.tree-panel {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.tree-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}
.tree-panel__kind {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.tree-panel__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
.tree-panel__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-2);
}
</style>
