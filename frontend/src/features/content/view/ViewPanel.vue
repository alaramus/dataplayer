<script setup lang="ts">
import { computed } from "vue"

import type { ContentRequest, NodeRepresentation, ViewPage } from "@/client"
import { reloadedBy } from "@/features/catalog/actions"
import type { ActionOutcome } from "@/features/catalog/actions"
import { REPRESENTATION_ICONS } from "@/features/catalog/nodes"
import { useContent } from "@/features/content/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { errorKindOf, messageOf, statusOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppIconButton, AppSpinner, AppStateTag, AppToolbarRule } from "@/shared/ui"
import { useSourceChangesStore } from "@/stores/sourceChanges"

import ViewActions from "./ViewActions.vue"

import ViewBlock from "./ViewBlock.vue"
import ViewValue from "./ViewValue.vue"
import { useOpenLinkedNode } from "./openNode"
import { otherRepresentations } from "./view"

/**
 * A node's document as its source says what it means (D419).
 *
 * Knows no source: every block is drawn by its kind, and a new source's view
 * is a function in its adapter and nothing here. Other representations and
 * source-owned pages open tabs of their own; the JSON is one of the
 * representations. Every command here is an icon with its title as a tooltip
 * (D424).
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
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

function show(other: NodeRepresentation) {
  workspace.openRepresentation({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    // Named as a page is: the view's tab keeps the node's bare name.
    title: `${props.title} — ${other.title}`,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    representations: [other],
    describable: false,
  })
}

function openPage(page: ViewPage) {
  const [preferred] = page.representations
  if (preferred === undefined) return
  workspace.openRepresentation({
    connectorId: props.connectorId,
    nodeId: page.node_id,
    title: `${props.title} — ${page.title}`,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    representations: page.representations,
    describable: false,
  })
}

function iconFor(page: ViewPage) {
  return page.icon ?? REPRESENTATION_ICONS[page.representations[0]?.kind ?? "table"]
}

const changes = useSourceChangesStore()

/**
 * After an action from the head: the catalog hears of it, and the view reads
 * the node again. A node that is gone — a removed container — takes its tab
 * with it rather than leaving a tab that says it cannot be read (D424).
 */
async function actionDone(outcome: ActionOutcome) {
  if (outcome.done.length === 0) return
  if (reloadedBy(outcome).length > 0) changes.announce(props.connectorId)
  const read = await content.refetch()
  if (read.isError && statusOf(read.error) === 404) workspace.closeTab(props.panelId)
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
        <ViewActions
          :connector-id="connectorId"
          :node-id="nodeId"
          :node-label="title"
          @done="actionDone"
        />
        <AppIconButton
          v-for="other in others"
          :key="other.kind"
          :icon="REPRESENTATION_ICONS[other.kind]"
          :tooltip="other.title"
          :data-testid="`view-show-${other.kind}`"
          @click="show(other)"
        />
        <AppIconButton
          v-for="(page, index) in view?.pages ?? []"
          :key="page.node_id"
          :icon="iconFor(page)"
          :tooltip="page.title"
          :data-testid="`view-page-${index}`"
          @click="openPage(page)"
        />
        <AppToolbarRule v-if="others.length > 0 || (view?.pages ?? []).length > 0" />
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
      class="view-panel__body dp-panel-scroll"
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
