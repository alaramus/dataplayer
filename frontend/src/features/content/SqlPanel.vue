<script setup lang="ts">
import { computed } from "vue"

import type { ContentRequest } from "@/client"
import CodeEditor from "@/features/content/CodeEditor.vue"
import { useContent } from "@/features/content/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppSpinner } from "@/shared/ui"

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  tableTitle?: string
}>()

const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({
  node_id: props.nodeId,
  representation: "sql",
}))
const content = useContent(connectorId, request)
const errorKind = computed(() => errorKindOf(content.error.value))
const workspace = useWorkspaceActions()
const ddl = computed(() => (content.data.value?.kind === "sql" ? content.data.value : null))
const error = computed(() =>
  content.isError.value ? messageOf(content.error.value, "Could not read this DDL") : ""
)

useReloadable(() => props.panelId, async () => {
  await content.refetch()
})

function showTable() {
  workspace.openRows({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    describable: true,
  })
}
</script>

<template>
  <div class="sql-panel">
    <div class="sql-panel__head">
      <span class="sql-panel__kind">SQL · read only</span>
      <div class="sql-panel__actions">
        <AppButton
          v-if="tableTitle"
          variant="quiet"
          size="sm"
          icon="grid_on"
          :label="tableTitle"
          data-testid="sql-view-table"
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
      data-testid="sql-error"
    >
      {{ error }}
    </SourceErrorBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <div
      v-else-if="ddl"
      class="sql-panel__body"
    >
      <AppBanner
        v-if="ddl.notice"
        tone="warning"
        class="sql-panel__notice"
        data-testid="sql-notice"
      >
        {{ ddl.notice }}
      </AppBanner>
      <CodeEditor
        :model-value="ddl.text"
        :filename="`${title}.sql`"
        language-hint="sql"
        readonly
        class="sql-panel__editor"
        data-testid="sql-editor"
      />
    </div>
  </div>
</template>

<style scoped>
.sql-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
}
.sql-panel__actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.sql-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 8px;
  border-bottom: 1px solid var(--dp-border-faint);
}
.sql-panel__kind {
  color: var(--dp-text-muted);
  font-size: 11px;
}
.sql-panel__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: 8px;
}
.sql-panel__notice {
  flex: none;
  margin-bottom: 8px;
}
.sql-panel__editor {
  flex: 1;
  min-height: 0;
}
</style>
