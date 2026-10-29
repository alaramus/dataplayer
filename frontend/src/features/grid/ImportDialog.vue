<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { ColumnPair, FetchColumn, ImportPreview } from "@/client"
import NodePicker from "@/features/catalog/NodePicker.vue"
import type { PickedNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
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
  /**
   * The source when it is already known — a Paste brings it from the
   * clipboard (D166) — so there is nothing to pick.
   */
  source?: { connectorId: string; nodeId: string; label: string; columns: FetchColumn[] } | null
  /** What this relation is called, where the dialog is not opened from its grid. */
  targetLabel?: string
  /**
   * The pairs chosen before, to start from rather than same-named columns: a
   * pipeline's link keeps them and opens this again on them (D176).
   */
  kept?: readonly ColumnPair[] | null
  /** The button's word, where it keeps a choice rather than bringing rows in. */
  actionLabel?: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [value: { connectorId: string; nodeId: string; columns: ColumnPair[] }]
}>()

const sourceId = ref("")
const chosen = ref<{ id: string; name: string } | null>(null)
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
    const known = props.source
    if (known) {
      take(known.connectorId, { id: known.nodeId, name: known.label }, known.columns)
    }
  },
  { immediate: true }
)

/** What the picker found. */
function picked(source: PickedNode | null) {
  take(source?.connectorId ?? "", source?.node ?? null, source?.columns ?? [])
}

/** The source, and the pairing it suggests to start from. */
function take(
  connectorId: string,
  node: { id: string; name: string } | null,
  columns: FetchColumn[]
) {
  preview.value = null
  sourceId.value = connectorId
  chosen.value = node === null ? null : { id: node.id, name: node.name }
  sourceColumns.value = columns
  // Same-named columns are offered as a starting point, never applied
  // silently: the reader confirms every pair before anything is read.
  const names = new Set(sourceColumns.value.map((column) => column.name))
  const before = props.kept ?? null
  pairs.value = Object.fromEntries(
    props.targetColumns.flatMap((column) => {
      const source = before === null
        ? column.name
        : before.find((pair) => pair.target === column.name)?.source
      return source !== undefined && names.has(source) ? [[column.name, source]] : []
    })
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
  if (filled === 0) return t("grid.import.nothing_paired")
  return t("grid.import.filled", { filled, total: props.targetColumns.length })
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
    trouble.value = messageOf(error, t("grid.import.preview_failed"))
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
    :title="t('grid.toolbar.commands.import')"
    :subtitle="
      source
        ? t('grid.import.subtitle_from', { source: source.label, target: targetLabel ?? t('grid.import.this_relation') })
        : t('grid.import.subtitle')
    "
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
        v-if="!source"
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
          {{ t('grid.import.target_column') }}
        </template>
        <template #to>
          {{ t('grid.import.filled_from') }}
          <span class="import__source">{{ chosen?.name ?? t('grid.import.other_source') }}</span>
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
                { label: t('grid.import.left_as_is'), value: '' },
                ...sourceColumns.map((item) => ({ label: item.name, value: item.name })),
              ]"
              :aria-label="t('grid.import.pair_aria', { column: column.name })"
              compact
              :data-testid="`grid-import-pair-${column.name}`"
              @update:model-value="pairs[column.name] = String($event)"
            />
          </template>
        </AppPairsRow>
      </AppPairs>

      <template v-if="preview !== null">
        <div class="import__title dp-overline">
          {{ t('grid.import.preview_title') }}
        </div>
        <AppTable
          :rows="preview.rows.map((row, index) => ({ index, ...Object.fromEntries(preview!.columns.map((name, at) => [name, row[at]])) }))"
          :columns="preview.columns.map((name) => ({ name, label: name, field: name, align: 'left' as const }))"
          row-key="index"
          compact
          :paged="false"
          :empty-text="t('grid.no_rows')"
        />
        <div
          v-if="preview.more"
          class="import__more"
        >
          {{ t('grid.import.more') }}
        </div>
      </template>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        :disable="running"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        variant="secondary"
        :label="t('grid.import.preview')"
        :disable="!ready || running"
        data-testid="grid-import-preview"
        @click="showPreview"
      />
      <AppButton
        :label="actionLabel ?? t('grid.import.run')"
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
  margin-inline-start: var(--dp-space-2);
  font-size: var(--dp-font-size-xs);
  color: var(--dp-text-muted);
}

/* The preview is headed the way the pairs are. */


.import__more {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
</style>
