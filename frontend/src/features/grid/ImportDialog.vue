<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { ColumnPair, FetchColumn, ImportPreview } from "@/client"
import type { CatalogNode } from "@/features/catalog/nodes"
import { useConnectors } from "@/features/connectors/api"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppSection,
  AppSelect,
  AppSpinner,
  AppTable,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  /** The relation being written: this connector, this node. */
  connectorId: string
  nodeId: string
  /** The columns of this relation that the source will accept a value for. */
  targetColumns: FetchColumn[]
  running: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [value: { connectorId: string; nodeId: string; columns: ColumnPair[] }]
}>()

const connectors = useConnectors()
const sourceId = ref("")
const trail = ref<CatalogNode[]>([])
const nodes = ref<CatalogNode[]>([])
const browsing = ref(false)
const chosen = ref<CatalogNode | null>(null)
const sourceColumns = ref<FetchColumn[]>([])
const pairs = ref<Record<string, string>>({})
const preview = ref<ImportPreview | null>(null)
const trouble = ref("")

const sources = computed(() =>
  (connectors.data.value?.data ?? [])
    .filter((connector) => connector.enabled)
    .map((connector) => ({ label: connector.name, value: connector.id }))
)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    sourceId.value = ""
    trail.value = []
    nodes.value = []
    chosen.value = null
    sourceColumns.value = []
    pairs.value = {}
    preview.value = null
    trouble.value = ""
  },
  { immediate: true }
)

async function openLevel(node: CatalogNode | null) {
  if (sourceId.value === "") return
  browsing.value = true
  trouble.value = ""
  try {
    const answer = await ConnectorsService.readCatalog({
      path: { connector_id: sourceId.value },
      query: node === null ? {} : { node_id: node.id },
    })
    nodes.value = answer.data
  } catch (error) {
    trouble.value = messageOf(error, "Could not read that source")
  } finally {
    browsing.value = false
  }
}

watch(sourceId, async () => {
  trail.value = []
  chosen.value = null
  sourceColumns.value = []
  pairs.value = {}
  preview.value = null
  await openLevel(null)
})

async function step(node: CatalogNode) {
  if (node.kind === "file") {
    await choose(node)
    return
  }
  trail.value = [...trail.value, node]
  await openLevel(node)
}

async function back() {
  const shorter = trail.value.slice(0, -1)
  trail.value = shorter
  await openLevel(shorter.at(-1) ?? null)
}

/** The source's own columns, read the way any other page of it is read. */
async function choose(node: CatalogNode) {
  chosen.value = node
  preview.value = null
  trouble.value = ""
  try {
    const answer = await ConnectorsService.fetchRows({
      path: { connector_id: sourceId.value },
      body: { node_id: node.id, limit: 1 },
    })
    sourceColumns.value = answer.data.columns
    // Same-named columns are offered as a starting point, never applied
    // silently: the reader confirms every pair before anything is read.
    const names = new Set(answer.data.columns.map((column) => column.name))
    pairs.value = Object.fromEntries(
      props.targetColumns
        .filter((column) => names.has(column.name))
        .map((column) => [column.name, column.name])
    )
  } catch (error) {
    trouble.value = messageOf(error, "Could not read that file as rows")
    sourceColumns.value = []
  }
}

const columnPairs = computed<ColumnPair[]>(() =>
  Object.entries(pairs.value)
    .filter(([, source]) => source !== "")
    .map(([target, source]) => ({ source, target }))
)

const here = computed(() =>
  trail.value.length === 0
    ? "Pick a file"
    : trail.value.map((node) => node.name).join(" / ")
)

const ready = computed(() => chosen.value !== null && columnPairs.value.length > 0)

async function showPreview() {
  if (!ready.value || chosen.value === null) return
  trouble.value = ""
  try {
    const answer = await ConnectorsService.previewImport({
      path: { connector_id: props.connectorId },
      body: {
        node_id: props.nodeId,
        source_connector_id: sourceId.value,
        source_node_id: chosen.value.id,
        columns: columnPairs.value,
      },
    })
    preview.value = answer.data
  } catch (error) {
    trouble.value = messageOf(error, "Could not read those rows")
  }
}

defineExpose({ showPreview })

function run() {
  if (!ready.value || chosen.value === null) return
  emit("run", {
    connectorId: sourceId.value,
    nodeId: chosen.value.id,
    columns: columnPairs.value,
  })
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Bring rows in"
    subtitle="From another source of yours, into this relation"
    size="lg"
    data-testid="grid-import-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="grid-import-error"
      >
        {{ error }}
      </AppBanner>
      <AppBanner
        v-if="trouble"
        tone="warning"
        data-testid="grid-import-trouble"
      >
        {{ trouble }}
      </AppBanner>
      <AppSelect
        :model-value="sourceId"
        :options="sources"
        label="Source"
        :loading="connectors.isFetching.value"
        data-testid="grid-import-source"
        @update:model-value="sourceId = String($event)"
      />

      <template v-if="sourceId !== ''">
        <div class="import__where">
          <AppButton
            v-if="trail.length > 0"
            label="Back"
            variant="quiet"
            size="sm"
            data-testid="grid-import-back"
            @click="back"
          />
          <span>{{ chosen === null ? here : chosen.name }}</span>
        </div>
        <AppSpinner v-if="browsing" />
        <ul
          v-else-if="chosen === null"
          class="import__nodes"
        >
          <li
            v-for="node in nodes"
            :key="node.id"
          >
            <AppButton
              :label="node.name"
              variant="quiet"
              size="sm"
              :data-testid="`grid-import-node-${node.name}`"
              @click="step(node)"
            />
          </li>
        </ul>
        <AppEmptyState
          v-if="!browsing && chosen === null && nodes.length === 0"
          text="Nothing here"
        />
      </template>

      <template v-if="sourceColumns.length > 0">
        <div class="import__title">
          Which column fills which
        </div>
        <div
          v-for="column in targetColumns"
          :key="column.name"
          class="import__pair"
        >
          <AppSelect
            :model-value="pairs[column.name] ?? ''"
            :options="[
              { label: '—', value: '' },
              ...sourceColumns.map((item) => ({ label: item.name, value: item.name })),
            ]"
            :label="column.name"
            compact
            :data-testid="`grid-import-pair-${column.name}`"
            @update:model-value="pairs[column.name] = String($event)"
          />
        </div>
      </template>

      <template v-if="preview !== null">
        <div class="import__title">
          The first rows, as they would arrive
        </div>
        <AppTable
          :rows="preview.rows.map((row, index) => ({ index, ...Object.fromEntries(preview!.columns.map((name, at) => [name, row[at]])) }))"
          :columns="preview.columns.map((name) => ({ name, label: name, field: name, align: 'left' as const }))"
          row-key="index"
          compact
          :paged="false"
          empty-text="No rows"
        />
        <div v-if="preview.more">
          The source holds more than these.
        </div>
      </template>
    </AppSection>
    <template #actions>
      <AppButton
        variant="secondary"
        label="Cancel"
        :disable="running"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        variant="secondary"
        label="Preview"
        :disable="!ready || running"
        data-testid="grid-import-preview"
        @click="showPreview"
      />
      <AppButton
        label="Bring in"
        :disable="!ready"
        :loading="running"
        data-testid="grid-import-run"
        @click="run"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.import__title {
  font-weight: 600;
}
.import__where {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.import__nodes {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 180px;
  overflow: auto;
}
.import__pair {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
