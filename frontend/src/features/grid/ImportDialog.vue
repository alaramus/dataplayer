<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { ColumnPair, FetchColumn, ImportPreview } from "@/client"
import NodePicker from "@/features/catalog/NodePicker.vue"
import type { CatalogNode, PickedNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppForm, AppSelect, AppTable } from "@/shared/ui"
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

      <div
        v-if="sourceColumns.length > 0"
        class="import__columns"
        data-testid="grid-import-columns"
      >
        <div class="import__legend">
          <span>Column in this relation</span>
          <span aria-hidden="true" />
          <span>
            Filled from
            <span class="import__source">{{ chosen?.name ?? "the other source" }}</span>
          </span>
          <span
            class="import__tally"
            data-testid="grid-import-tally"
          >{{ tally }}</span>
        </div>
        <div
          v-for="column in targetColumns"
          :key="column.name"
          class="import__pair"
          :class="{ 'import__pair--idle': !pairs[column.name] }"
          :data-testid="`grid-import-row-${column.name}`"
        >
          <span class="import__target">
            {{ column.name }}
            <span class="import__type">{{ column.type.sql }}</span>
          </span>
          <!-- Pointing at what is filled rather than at what fills it: the
               rows are the columns of this relation, and the eye follows the
               fixed side to the side that changes. -->
          <q-icon
            name="arrow_back"
            size="16px"
            class="import__arrow"
            aria-hidden="true"
          />
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
        </div>
      </div>

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
/* The same shape as the columns of "Create table from file", because it is
   the same question asked twice: which column becomes which. A row was a
   single select labelled with the column it filled, which put the name inside
   a compact field narrow enough to truncate it to one letter. On the window's
   surface rather than in a card of its own (D131). */
.import__legend,
.import__pair {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) 24px minmax(160px, 1.2fr);
  align-items: center;
  gap: var(--dp-space-2);
}

.import__legend {
  grid-template-columns: minmax(160px, 1fr) 24px minmax(160px, 1.2fr) auto;
  padding-bottom: var(--dp-space-1);
  border-bottom: 1px solid var(--dp-border-faint);
}

/* The preview is headed the way the pairs are. */
.import__legend,
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

.import__tally {
  letter-spacing: 0;
  text-transform: none;
  font-weight: 400;
}

/* A name is a name: the legend around it is small capitals, and running a
   relation called `app_users` through that spelling changes what it is. */
.import__source {
  text-transform: none;
  letter-spacing: 0;
}

.import__pair { padding: var(--dp-space-1) 0; }
.import__pair + .import__pair { border-top: 1px solid var(--dp-border-faint); }

.import__target { overflow-wrap: anywhere; }

/* The type of the column being filled, because what may fill it is the
   question this dialog asks and the answer depends on it. */
.import__type {
  margin-left: var(--dp-space-2);
  font-size: 11px;
  color: var(--dp-text-faint);
}

.import__arrow { color: var(--dp-text-faint); justify-self: center; }

/* A column nothing fills keeps its row: which columns this relation has is
   part of what the screen says. The arrow goes, because it points nowhere. */
.import__pair--idle .import__target { color: var(--dp-text-muted); }
.import__pair--idle .import__arrow { visibility: hidden; }

/* A narrow form keeps the pairs side by side and drops the arrow between them,
   which is the column that cannot shrink. */
@container app-form (max-width: 480px) {
  .import__legend,
  .import__pair {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  }
  .import__legend > [aria-hidden="true"],
  .import__arrow {
    display: none;
  }
  .import__tally {
    grid-column: 1 / -1;
  }
}
</style>
