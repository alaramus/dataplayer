<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { ColumnPair, FetchColumn, ImportPreview } from "@/client"
import NodePicker from "@/features/catalog/NodePicker.vue"
import type { CatalogNode, PickedNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppForm, AppPairs, AppPairsRow, AppSelect, AppTable } from "@/shared/ui"
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

const sourceId = ref("")
const chosen = ref<CatalogNode | null>(null)
const sourceColumns = ref<FetchColumn[]>([])
const pairs = ref<Record<string, string>>({})
const preview = ref<ImportPreview | null>(null)
const trouble = ref("")

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    sourceId.value = ""
    chosen.value = null
    sourceColumns.value = []
    pairs.value = {}
    preview.value = null
    trouble.value = ""
  },
  { immediate: true }
)

/** What the picker found, and the pairing it suggests to start from. */
function picked(source: PickedNode | null) {
  preview.value = null
  sourceId.value = source?.connectorId ?? ""
  chosen.value = source?.node ?? null
  sourceColumns.value = source?.columns ?? []
  // Same-named columns are offered as a starting point, never applied
  // silently: the reader confirms every pair before anything is read.
  const names = new Set(sourceColumns.value.map((column) => column.name))
  pairs.value = Object.fromEntries(
    props.targetColumns
      .filter((column) => names.has(column.name))
      .map((column) => [column.name, column.name])
  )
}

const columnPairs = computed<ColumnPair[]>(() =>
  Object.entries(pairs.value)
    .filter(([, source]) => source !== "")
    .map(([target, source]) => ({ source, target }))
)

const ready = computed(() => chosen.value !== null && columnPairs.value.length > 0)

/**
 * What the block of pairs says about itself, in one line.
 *
 * A compact field keeps no room under it for a message, and the button this
 * refuses is at the other end of the dialog — so the count and the reason go
 * together above them all.
 */
const tally = computed(() => {
  const filled = columnPairs.value.length
  if (filled === 0) return "nothing paired yet"
  return `${filled} of ${props.targetColumns.length} filled`
})

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
    size="wide-form"
    sizing="stable"
    data-testid="grid-import-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
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
      <NodePicker
        :key="modelValue ? 'open' : 'closed'"
        testid="grid-import"
        @pick="picked"
        @trouble="trouble = $event"
      />

      <!-- Pointing at what is filled rather than at what fills it: the rows
           are the columns of this relation, and the eye follows the fixed side
           to the side that changes. -->
      <AppPairs
        v-if="sourceColumns.length > 0"
        arrow="back"
        data-testid="grid-import-columns"
      >
        <template #from>
          Column in this relation
        </template>
        <template #to>
          Filled from
          <span class="import__source">{{ chosen?.name ?? "the other source" }}</span>
        </template>
        <template #aside>
          <span data-testid="grid-import-tally">{{ tally }}</span>
        </template>
        <AppPairsRow
          v-for="column in targetColumns"
          :key="column.name"
          :idle="!pairs[column.name]"
          :data-testid="`grid-import-row-${column.name}`"
        >
          <template #from>
            {{ column.name }}
            <span class="import__type">{{ column.type.sql }}</span>
          </template>
          <template #to>
            <AppSelect
              :model-value="pairs[column.name] ?? ''"
              :options="[
                { label: 'Left as it is', value: '' },
                ...sourceColumns.map((item) => ({ label: item.name, value: item.name })),
              ]"
              :aria-label="`Column that fills ${column.name}`"
              compact
              :data-testid="`grid-import-pair-${column.name}`"
              @update:model-value="pairs[column.name] = String($event)"
            />
          </template>
        </AppPairsRow>
      </AppPairs>

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
        <div
          v-if="preview.more"
          class="import__more"
        >
          The source holds more than these.
        </div>
      </template>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
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
/* A name is a name: the legend around it is small capitals, and running a
   relation called `app_users` through that spelling changes what it is. */
.import__source {
  text-transform: none;
  letter-spacing: 0;
}

/* The type of the column being filled, because what may fill it is the
   question this dialog asks and the answer depends on it. */
.import__type {
  margin-left: var(--dp-space-2);
  font-size: 11px;
  color: var(--dp-text-faint);
}

/* The preview is headed the way the pairs are. */
.import__title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dp-text-muted);
}

.import__more {
  font-size: 12px;
  color: var(--dp-text-muted);
}
</style>
