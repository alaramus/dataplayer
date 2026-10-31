<script setup lang="ts">
import { computed } from "vue"

import type { ContentRequest } from "@/client"
import JsonTreeNode from "@/features/content/JsonTreeNode.vue"
import { useContent } from "@/features/content/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppSpinner } from "@/shared/ui"

/**
 * A source's own description of a node, drawn as a JSON tree (D295).
 *
 * Read only: what a MongoDB collection's options, validator and indexes are,
 * or the pipeline a report runs. A file's JSON is its text, and opens in the
 * editor instead.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
}>()

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
      <span class="tree-panel__kind">{{ t("content.tree.kind") }}</span>
      <!-- One block, so the head puts it at the end as the other panels do;
           the commands are several elements, each a flex item of their own. -->
      <div class="tree-panel__commands">
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
