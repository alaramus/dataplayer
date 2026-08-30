<script setup lang="ts">
import { computed, ref } from "vue"

import type { ContentRequest } from "@/client"
import { useContent } from "@/features/content/api"
import JsonValueView from "@/features/content/JsonValueView.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppEmptyState, AppSpinner } from "@/shared/ui"

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  representation: "text" | "json" | "jsonl"
  tableTitle?: string
}>()

const connectorId = computed(() => props.connectorId)
const offset = ref(0)
const previousOffsets = ref<number[]>([])
const pageSize = 50
const request = computed<ContentRequest>(() => ({
  node_id: props.nodeId,
  representation: props.representation,
  limit: pageSize,
  offset: props.representation === "jsonl" ? offset.value : 0,
}))
const content = useContent(connectorId, request)
const workspace = useWorkspaceActions()

useReloadable(props.panelId, async () => {
  await content.refetch()
})

const error = computed(() =>
  content.isError.value ? messageOf(content.error.value, "Could not read this file") : ""
)
const notice = computed(() => {
  const value = content.data.value
  return value !== undefined && "notice" in value ? value.notice : undefined
})
const rangeLabel = computed(() => {
  const value = content.data.value
  if (value === undefined || value.kind !== "jsonl" || value.items.length === 0) {
    return "No records on this page"
  }
  return `Records ${offset.value + 1}–${offset.value + value.items.length}`
})

function showTable() {
  workspace.openRows({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    describable: false,
  })
}

function previous() {
  offset.value = previousOffsets.value.pop() ?? 0
}

function next() {
  const value = content.data.value
  if (value === undefined || value.kind !== "jsonl" || value.items.length === 0) return
  previousOffsets.value.push(offset.value)
  offset.value += value.items.length
}
</script>

<template>
  <div class="content-panel">
    <div class="content-panel__head">
      <span class="content-panel__kind">
        {{ representation === "jsonl" ? "JSON lines" : representation.toUpperCase() }}
      </span>
      <AppButton
        v-if="tableTitle"
        variant="secondary"
        size="sm"
        icon="grid_on"
        :label="tableTitle"
        data-testid="content-view-table"
        @click="showTable"
      />
    </div>

    <AppBanner v-if="error" tone="error" data-testid="content-error">
      {{ error }}
    </AppBanner>

    <AppSpinner v-else-if="content.isPending.value" />

    <template v-else-if="content.data.value">
      <AppBanner
        v-if="notice"
        tone="warning"
        class="content-panel__notice"
        data-testid="content-notice"
      >
        {{ notice }}
      </AppBanner>

      <div v-if="content.data.value.kind === 'text'" class="content-panel__body">
        <pre
          class="content-panel__source"
          data-testid="text-content"
          v-text="content.data.value.text"
        />
        <AppBanner v-if="content.data.value.truncated" tone="info" class="content-panel__bounded">
          This preview stops after the first bounded part of the file.
        </AppBanner>
      </div>

      <div v-else-if="content.data.value.kind === 'json'" class="content-panel__body">
        <JsonValueView
          v-if="content.data.value.value"
          :value="content.data.value.value"
          data-testid="json-content"
        />
        <pre
          v-else
          class="content-panel__source"
          data-testid="json-source"
          v-text="content.data.value.source_text ?? ''"
        />
        <AppBanner v-if="content.data.value.truncated" tone="info" class="content-panel__bounded">
          This source preview is truncated.
        </AppBanner>
      </div>

      <div v-else class="content-panel__jsonl" data-testid="jsonl-content">
        <AppEmptyState
          v-if="content.data.value.items.length === 0"
          text="No JSON values on this page"
        />
        <article
          v-for="item in content.data.value.items"
          :key="item.line_number"
          class="content-panel__record"
        >
          <div class="content-panel__line">Line {{ item.line_number }}</div>
          <AppBanner v-if="item.notice" tone="warning">
            {{ item.notice }}
          </AppBanner>
          <JsonValueView v-if="item.value" :value="item.value" />
          <pre v-else class="content-panel__source" v-text="item.source_text ?? ''" />
        </article>
        <div class="content-panel__pager">
          <AppButton
            variant="quiet"
            size="sm"
            label="Previous"
            :disable="previousOffsets.length === 0"
            data-testid="content-previous"
            @click="previous"
          />
          <span>{{ rangeLabel }}</span>
          <AppButton
            variant="quiet"
            size="sm"
            label="Next"
            :disable="!content.data.value.has_more"
            data-testid="content-next"
            @click="next"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.content-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
}
.content-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 8px;
  border-bottom: 1px solid var(--dp-border-faint);
}
.content-panel__kind,
.content-panel__line {
  color: var(--dp-text-muted);
  font-size: 11px;
}
.content-panel__body,
.content-panel__jsonl {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
.content-panel__notice,
.content-panel__bounded {
  margin: 8px;
}
.content-panel__source {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}
.content-panel__record {
  padding: 8px 0 12px;
  border-bottom: 1px solid var(--dp-border-faint);
}
.content-panel__line {
  margin-bottom: 4px;
}
.content-panel__pager {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px;
  border-top: 1px solid var(--dp-border);
  background: var(--dp-surface);
  color: var(--dp-text-muted);
  font-size: 11px;
}
</style>
