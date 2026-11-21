<script setup lang="ts">
import { computed } from "vue"

import type { ContentRequest, NodeRepresentation } from "@/client"
import { REPRESENTATION_ICONS } from "@/features/catalog/nodes"
import { useContent } from "@/features/content/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppButton, AppSpinner, AppStateTag } from "@/shared/ui"

import ViewBlock from "./ViewBlock.vue"
import ViewValue from "./ViewValue.vue"
import { useOpenLinkedNode } from "./openNode"
import { otherRepresentations } from "./view"

/**
 * A node's document as its source says what it means (D419).
 *
 * Knows no source: every block is drawn by its kind, and a new source's view
 * is a function in its adapter and nothing here. Each other way the node
 * opens is a button, and switches this tab to it; the JSON is one of them.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  representations?: NodeRepresentation[]
}>()

const workspace = useWorkspaceActions()
const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({ node_id: props.nodeId, representation: "view" }))
const content = useContent(connectorId, request)
const errorKind = computed(() => errorKindOf(content.error.value))
const view = computed(() => (content.data.value?.kind === "view" ? content.data.value : null))
const error = computed(() =>
  content.isError.value ? messageOf(content.error.value, t("content.view.could_not_open")) : ""
)
const heading = computed(
  () => props.representations?.find((one) => one.kind === "view")?.title ?? t("content.view.heading")
)
const others = computed(() => otherRepresentations(props.representations, "view"))
const openLinked = useOpenLinkedNode(() => props.connectorId)

function show(kind: NodeRepresentation["kind"]) {
  workspace.switchRepresentation(props.panelId, kind)
}

useReloadable(() => props.panelId, async () => {
  await content.refetch()
})
</script>

<template>
  <div class="view-panel">
    <div class="view-panel__head">
      <span class="view-panel__kind">{{ heading }}</span>
      <div class="view-panel__commands">
        <AppButton
          v-for="other in others"
          :key="other.kind"
          variant="quiet"
          size="sm"
          :icon="REPRESENTATION_ICONS[other.kind]"
          :label="other.title"
          layout="toolbar"
          :data-testid="`view-show-${other.kind}`"
          @click="show(other.kind)"
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
      data-testid="view-error"
    >
      {{ error }}
    </SourceErrorBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <div
      v-else-if="view !== null"
      class="view-panel__body"
      data-testid="view-body"
    >
      <header class="view-panel__header">
        <h2
          class="view-panel__title"
          data-testid="view-title"
        >
          {{ view.header.title }}
        </h2>
        <AppStateTag
          v-if="view.header.state"
          :label="view.header.state.word"
          :tone="view.header.state.tone"
          data-testid="view-state"
        />
        <ViewValue
          v-if="view.header.subtitle"
          class="view-panel__subtitle"
          :value="view.header.subtitle"
          @open="openLinked"
        />
      </header>
      <ViewBlock
        v-for="(block, index) in view.blocks"
        :key="index"
        :block="block"
        @open="openLinked"
      />
    </div>
  </div>
</template>

<style scoped>
.view-panel {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.view-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}
.view-panel__kind {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.view-panel__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
.view-panel__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-2) var(--dp-space-3);
}
.view-panel__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--dp-space-1) var(--dp-space-3);
}
.view-panel__title {
  font-size: var(--dp-font-size-lg);
  font-weight: 600;
  overflow-wrap: anywhere;
}
.view-panel__subtitle {
  color: var(--dp-text-muted);
}
</style>
