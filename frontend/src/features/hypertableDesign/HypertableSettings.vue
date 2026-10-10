<script setup lang="ts">
import { computed, onBeforeUnmount, ref, toRef, watch } from "vue"

import type { ActionPreview, HypertableDesign } from "@/client"
import { usePreviewAction } from "@/features/catalog/api"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppIconButton,
  AppInput,
  AppNumberInput,
  AppRadioGroup,
  AppSelect,
  AppSpinner,
  AppToggle,
  appIcons,
  useConfirm,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useHypertableState } from "./api"
import { clocksFor, completed, draftFrom, nowKey, retimed } from "./draft"
import type { Draft, DurationUnit, NowTemplate, PolicyMode } from "./draft"

const props = defineProps<{
  modelValue: boolean
  connectorId: string
  nodeId: string
  nodeLabel: string
  /** The action this editor fills; the plan is asked of it (D207). */
  actionName: string
  running: boolean
  error: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [value: { nodeId: string; params: Record<string, unknown>; fingerprint: string; asJob: boolean }]
}>()

const state = useHypertableState(toRef(props, "connectorId"), toRef(props, "nodeId"), toRef(props, "modelValue"))
const draft = ref<Draft | null>(null)

watch(
  () => state.data.value,
  (answer) => {
    draft.value = answer ? draftFrom(answer) : null
  },
  { immediate: true }
)

const facts = computed(() => state.data.value)
/** An ordinary table: every plan starts by converting it (D207). */
const converting = computed(() => facts.value?.hypertable === false)
const confirm = useConfirm()
const reason = computed(() => facts.value?.reason ?? "")
const enabledNow = computed(() => facts.value?.design?.columnstore?.enabled === true)

/** How long the form is left alone before the source is asked again. */
const PLAN_DELAY_MS = 300
const previewAction = usePreviewAction()
const preview = ref<ActionPreview | null>(null)
const missing = ref("")
const planFailed = ref("")
const planning = ref(false)
let asked = 0
let timer: ReturnType<typeof setTimeout> | undefined

async function askPlan(design: HypertableDesign) {
  const mine = (asked += 1)
  planning.value = true
  try {
    const answer = await previewAction.mutateAsync({
      connectorId: props.connectorId,
      name: props.actionName,
      nodeId: props.nodeId,
      params: { design },
    })
    if (mine !== asked) return
    preview.value = answer
    planFailed.value = ""
  } catch (cause) {
    if (mine !== asked) return
    preview.value = null
    planFailed.value = messageOf(cause, "Could not plan this change")
  } finally {
    if (mine === asked) planning.value = false
  }
}

function schedulePlan() {
  if (timer !== undefined) clearTimeout(timer)
  asked += 1
  preview.value = null
  planFailed.value = ""
  const current = draft.value
  if (current === null) return
  const answer = completed(current)
  if ("missing" in answer) {
    missing.value = answer.missing
    planning.value = false
    return
  }
  missing.value = ""
  planning.value = true
  timer = setTimeout(() => void askPlan(answer.design), PLAN_DELAY_MS)
}

watch(draft, schedulePlan, { deep: true })
// A refused run leaves the source changed or busy, so the plan is asked again.
watch(
  () => props.error,
  (message) => {
    if (message !== "") schedulePlan()
  }
)
onBeforeUnmount(() => {
  if (timer !== undefined) clearTimeout(timer)
  asked += 1
})

const ready = computed(
  () =>
    !planning.value &&
    preview.value !== null &&
    !preview.value.blocked &&
    typeof preview.value.fingerprint === "string"
)

const asJob = computed(() => preview.value?.runs_as_job === true)
const applyLabel = computed(() =>
  asJob.value ? "Start conversion" : converting.value ? "Convert" : "Apply"
)

async function apply() {
  const current = draft.value
  const fingerprint = preview.value?.fingerprint
  if (current === null || !ready.value || typeof fingerprint !== "string") return
  const answer = completed(current)
  if ("missing" in answer) return
  const job = asJob.value
  // The one step nothing here can undo is asked about by itself, whatever else the plan holds.
  if (
    converting.value &&
    !(await confirm({
      title: "Convert to a hypertable?",
      message: job
        ? "The table is locked against reads and writes while its rows move into chunks, and " +
          "DataPlayer cannot turn it back into an ordinary table."
        : "DataPlayer cannot turn a hypertable back into an ordinary table.",
      confirmLabel: job ? "Start conversion" : "Convert",
      danger: true,
    }))
  ) {
    return
  }
  emit("run", { nodeId: props.nodeId, params: { design: answer.design }, fingerprint, asJob: job })
}

const timeColumns = computed(() =>
  (facts.value?.time_columns ?? []).map((column) => ({
    label: `${column.name} · ${column.type}`,
    value: column.name,
  }))
)
/** The column partitioning the table, or the one it is to be converted by. */
const timeColumn = computed(() =>
  (facts.value?.time_columns ?? []).find((column) => column.name === draft.value?.timeColumn)
)
/** Counted in the column's own values rather than in time (D207). */
const integer = computed(() => draft.value?.chunkInterval.unit === "integer")

function chooseTime(name: unknown) {
  const column = (facts.value?.time_columns ?? []).find((item) => item.name === name)
  if (draft.value && column && facts.value) draft.value = retimed(draft.value, column, facts.value)
}

const TEMPLATE_LABELS: Record<NowTemplate, string> = {
  epoch_seconds: "Seconds since 1970",
  epoch_milliseconds: "Milliseconds since 1970",
  epoch_microseconds: "Microseconds since 1970",
}
const templates = computed(() =>
  (timeColumn.value?.now_templates ?? []).map((value) => ({ label: TEMPLATE_LABELS[value], value }))
)
const clocks = computed(() =>
  clocksFor(facts.value?.now_functions, timeColumn.value?.type).map((item) => ({
    label: `${item.schema_name}.${item.name}()`,
    value: nowKey(item),
  }))
)
const nowModes = computed(() => {
  const current = facts.value?.design?.integer_now
  return [
    ...(current ? [] : [{ label: "None", value: "none" }]),
    ...(current?.kind === "current"
      ? [{ label: `Keep ${facts.value?.integer_now_name ?? "the current function"}()`, value: "current" }]
      : []),
    { label: "A function of this database", value: "existing" },
    ...(templates.value.length > 0 ? [{ label: "A new function from a template", value: "template" }] : []),
  ]
})
const estimate = computed(() => {
  const rows = facts.value?.row_estimate
  if (rows === null || rows === undefined) return "an unknown number of rows"
  return `about ${rows.toLocaleString()} rows`
})

const UNIT_LABELS: Record<DurationUnit, string> = {
  second: "seconds",
  minute: "minutes",
  hour: "hours",
  day: "days",
  week: "weeks",
  month: "months",
  year: "years",
}
const units = (list: readonly DurationUnit[] | undefined) =>
  (list ?? []).map((unit) => ({ label: UNIT_LABELS[unit], value: unit }))
const intervalUnits = computed(() => units(facts.value?.interval_units))
const policyUnits = computed(() => units(facts.value?.policy_units))
const mergeUnits = computed(() => units(facts.value?.merge_units))

const orderable = computed(() =>
  (facts.value?.columns ?? [])
    .filter((column) => column.orderable)
    .map((column) => ({ label: `${column.name} · ${column.type}`, value: column.name }))
)
const hashable = computed(() =>
  orderable.value.filter((choice) => choice.value !== facts.value?.time_column)
)

const segmentModes = computed(() => [
  ...(facts.value?.per_chunk_defaults === true || !enabledNow.value
    ? [{ label: "Chosen by TimescaleDB", value: "default" }]
    : []),
  { label: "None", value: "none" },
  { label: "These columns", value: "columns" },
])
const orderModes = computed(() => [
  ...(facts.value?.per_chunk_defaults === true || !enabledNow.value
    ? [{ label: "Chosen by TimescaleDB", value: "default" }]
    : []),
  { label: "These columns", value: "columns" },
])

function policyModes(current: string | undefined, verb: string) {
  return [
    { label: "None", value: "none" },
    { label: `${verb} chunks older than`, value: "older_than" },
    ...(current ? [{ label: `Keep as it is · ${current}`, value: "current" }] : []),
  ]
}
const retentionModes = computed(() => policyModes(facts.value?.retention?.description, "Drop"))
const columnstorePolicyModes = computed(() =>
  policyModes(facts.value?.columnstore_policy?.description, "Compress")
)
const indexes = computed(() => [
  { label: "None", value: "" },
  ...(facts.value?.indexes ?? []).map((name) => ({ label: name, value: name })),
])
const tablespaces = computed(() =>
  [...new Set([...(facts.value?.tablespaces ?? []), ...(facts.value?.design?.tablespaces ?? [])])].map(
    (name) => ({ label: name, value: name })
  )
)

function addHash() {
  draft.value?.hash.push({ column: "", partitions: 4, existing: false })
}
function addSparse() {
  draft.value?.sparseIndexes.push({ column: "", kind: "minmax" })
}
const sparseKinds = [
  { label: "minmax: the smallest and largest value", value: "minmax" },
  { label: "bloom: whether a value is there", value: "bloom" },
]
const columns = computed(() =>
  (facts.value?.columns ?? []).map((column) => ({ label: `${column.name} · ${column.type}`, value: column.name }))
)

function addOrder() {
  draft.value?.orderColumns.push({ column: "", descending: false, nullsFirst: false })
}
function setPolicy(target: "retention" | "columnstorePolicy", mode: string) {
  if (draft.value) draft.value[target].mode = mode as PolicyMode
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    size="xl"
    sizing="stable"
    :title="`${converting ? 'Convert to hypertable' : 'Hypertable settings'} — ${nodeLabel}`"
    data-testid="hypertable-settings"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="settings">
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="hypertable-error"
      >
        {{ error }}
      </AppBanner>
      <div
        v-if="state.isLoading.value"
        class="settings__waiting"
      >
        <AppSpinner />
      </div>
      <AppBanner
        v-else-if="state.error.value"
        tone="error"
      >
        {{ messageOf(state.error.value, "Could not read the hypertable") }}
      </AppBanner>
      <AppBanner
        v-else-if="reason"
        tone="warning"
        data-testid="hypertable-reason"
      >
        {{ reason }}
      </AppBanner>
      <div
        v-else-if="draft"
        class="settings__body"
      >
        <main
          class="settings__form"
          data-testid="hypertable-form"
        >
          <section class="settings__group">
            <strong>Chunks</strong>
            <template v-if="converting">
              <p class="settings__note">
                An ordinary table with {{ estimate }}. Choose the column it is partitioned by;
                TimescaleDB cannot change it afterwards.
              </p>
              <AppSelect
                :model-value="draft.timeColumn"
                :options="timeColumns"
                label="Time column"
                data-testid="time-column"
                @update:model-value="chooseTime"
              />
            </template>
            <p
              v-else
              class="settings__note"
            >
              Partitioned by time on {{ facts?.time_column }} ({{ facts?.time_column_type }}).
              TimescaleDB cannot change the time column.
            </p>
            <div class="settings__pair">
              <AppNumberInput
                v-model="draft.chunkInterval.amount"
                :label="integer ? 'Each chunk covers, in values of the time column' : 'Each chunk covers'"
                data-testid="chunk-interval-amount"
              />
              <AppSelect
                v-if="!integer"
                v-model="draft.chunkInterval.unit"
                :options="intervalUnits"
                label="Unit"
                data-testid="chunk-interval-unit"
              />
            </div>
            <div
              v-for="(item, at) in draft.hash"
              :key="at"
              class="settings__row"
              data-testid="hash-dimension"
            >
              <AppSelect
                v-model="item.column"
                :options="hashable"
                label="Hash column"
                :disable="item.existing"
              />
              <AppNumberInput
                v-model="item.partitions"
                label="Partitions"
              />
              <AppIconButton
                v-if="!item.existing"
                :icon="appIcons.deleteOutline"
                tooltip="Remove this hash dimension"
                @click="draft.hash.splice(at, 1)"
              />
            </div>
            <div class="settings__inline">
              <AppButton
                variant="quiet"
                :icon="appIcons.add"
                label="Hash dimension"
                :disable="facts?.has_chunks === true"
                data-testid="add-hash-dimension"
                @click="addHash"
              />
              <span
                v-if="facts?.has_chunks"
                class="settings__note"
              >A hash dimension can only be added while the {{ converting ? "table holds no rows" : "hypertable holds no chunks" }}.</span>
            </div>
          </section>

          <section class="settings__group">
            <AppToggle
              v-model="draft.columnstore"
              label="Columnstore"
              data-testid="columnstore-enabled"
            />
            <p
              v-if="facts?.compressed_chunks && draft.columnstore"
              class="settings__note"
            >
              Some chunks are compressed, so the columnstore stays on until they are decompressed.
            </p>
            <template v-if="draft.columnstore">
              <AppRadioGroup
                v-model="draft.segmentMode"
                :options="segmentModes"
                label="Segment by"
                data-testid="segment-mode"
              />
              <AppSelect
                v-if="draft.segmentMode === 'columns'"
                v-model="draft.segmentColumns"
                :options="orderable"
                label="Segment columns"
                multiple
                data-testid="segment-columns"
              />
              <AppRadioGroup
                v-model="draft.orderMode"
                :options="orderModes"
                label="Order by"
                data-testid="order-mode"
              />
              <template v-if="draft.orderMode === 'columns'">
                <div
                  v-for="(key, at) in draft.orderColumns"
                  :key="at"
                  class="settings__row"
                  data-testid="order-column"
                >
                  <AppSelect
                    v-model="key.column"
                    :options="orderable"
                    label="Column"
                  />
                  <AppCheckbox
                    v-model="key.descending"
                    label="Descending"
                  />
                  <AppCheckbox
                    v-model="key.nullsFirst"
                    label="Nulls first"
                  />
                  <AppIconButton
                    :icon="appIcons.deleteOutline"
                    tooltip="Remove this order column"
                    @click="draft.orderColumns.splice(at, 1)"
                  />
                </div>
                <div class="settings__inline">
                  <AppButton
                    variant="quiet"
                    :icon="appIcons.add"
                    label="Order column"
                    data-testid="add-order-column"
                    @click="addOrder"
                  />
                  <span class="settings__note">The time column is added last, descending, unless it is listed.</span>
                </div>
              </template>
              <template v-if="facts?.sparse_indexes_supported">
                <AppRadioGroup
                  v-model="draft.sparseMode"
                  :options="segmentModes"
                  label="Sparse indexes"
                  data-testid="sparse-mode"
                />
                <template v-if="draft.sparseMode === 'columns'">
                  <div
                    v-for="(item, at) in draft.sparseIndexes"
                    :key="at"
                    class="settings__row"
                    data-testid="sparse-index"
                  >
                    <AppSelect
                      v-model="item.column"
                      :options="columns"
                      label="Column"
                    />
                    <AppSelect
                      v-model="item.kind"
                      :options="sparseKinds"
                      label="Kind"
                    />
                    <AppIconButton
                      :icon="appIcons.deleteOutline"
                      tooltip="Remove this sparse index"
                      @click="draft.sparseIndexes.splice(at, 1)"
                    />
                  </div>
                  <div class="settings__inline">
                    <AppButton
                      variant="quiet"
                      :icon="appIcons.add"
                      label="Sparse index"
                      data-testid="add-sparse-index"
                      @click="addSparse"
                    />
                    <span class="settings__note">TimescaleDB keeps sparse indexes only beside named order columns.</span>
                  </div>
                </template>
              </template>
              <AppCheckbox
                v-if="!integer"
                v-model="draft.merge"
                label="Merge chunks as they are compressed"
                data-testid="merge-enabled"
              />
              <div
                v-if="draft.merge && !integer"
                class="settings__pair"
              >
                <AppNumberInput
                  v-model="draft.mergeInterval.amount"
                  label="Into chunks of"
                  hint="A whole multiple of the chunk interval"
                  data-testid="merge-amount"
                />
                <AppSelect
                  v-model="draft.mergeInterval.unit"
                  :options="mergeUnits"
                  label="Unit"
                />
              </div>
            </template>
          </section>

          <section
            v-if="integer"
            class="settings__group"
            data-testid="integer-now"
          >
            <strong>Current value</strong>
            <p class="settings__note">
              Age policies on an integer column need a function that says what the current value is:
              TimescaleDB calls it integer_now.
            </p>
            <AppSelect
              v-model="draft.now.mode"
              :options="nowModes"
              label="integer_now"
              data-testid="integer-now-mode"
            />
            <AppSelect
              v-if="draft.now.mode === 'existing'"
              v-model="draft.now.existing"
              :options="clocks"
              label="Function"
              hint="No arguments, stable, returning the column's type"
              data-testid="integer-now-function"
            />
            <div
              v-if="draft.now.mode === 'template'"
              class="settings__pair"
            >
              <AppSelect
                v-model="draft.now.template"
                :options="templates"
                label="Counts"
                data-testid="integer-now-template"
              />
              <AppInput
                v-model="draft.now.name"
                label="Function name"
                :hint="`Created in schema ${facts?.schema_name ?? ''}`"
                data-testid="integer-now-name"
              />
            </div>
          </section>

          <section class="settings__group">
            <strong>Policies</strong>
            <AppSelect
              :model-value="draft.retention.mode"
              :options="retentionModes"
              label="Retention"
              data-testid="retention-mode"
              @update:model-value="setPolicy('retention', String($event))"
            />
            <div
              v-if="draft.retention.mode === 'older_than'"
              class="settings__pair"
            >
              <AppNumberInput
                v-model="draft.retention.duration.amount"
                :label="integer ? 'Age, in values of the time column' : 'Age'"
                data-testid="retention-amount"
              />
              <AppSelect
                v-if="!integer"
                v-model="draft.retention.duration.unit"
                :options="policyUnits"
                label="Unit"
              />
            </div>
            <AppSelect
              :model-value="draft.columnstorePolicy.mode"
              :options="columnstorePolicyModes"
              label="Columnstore policy"
              :disable="!draft.columnstore"
              data-testid="columnstore-policy-mode"
              @update:model-value="setPolicy('columnstorePolicy', String($event))"
            />
            <div
              v-if="draft.columnstorePolicy.mode === 'older_than'"
              class="settings__pair"
            >
              <AppNumberInput
                v-model="draft.columnstorePolicy.duration.amount"
                :label="integer ? 'Age, in values of the time column' : 'Age'"
                data-testid="columnstore-policy-amount"
              />
              <AppSelect
                v-if="!integer"
                v-model="draft.columnstorePolicy.duration.unit"
                :options="policyUnits"
                label="Unit"
              />
            </div>
            <AppCheckbox
              v-if="facts?.compaction_supported"
              v-model="draft.compaction"
              label="Compaction policy: merge small compressed chunks"
              :disable="!draft.columnstore"
              data-testid="compaction-policy"
            />
            <AppSelect
              v-model="draft.reorderIndex"
              :options="indexes"
              label="Reorder chunks by index"
              :hint="facts?.reorder?.description"
              data-testid="reorder-index"
            />
          </section>

          <section class="settings__group">
            <strong>Tablespaces</strong>
            <AppSelect
              v-model="draft.tablespaces"
              :options="tablespaces"
              label="Place new chunks in"
              hint="Existing chunks stay where they are"
              multiple
              data-testid="tablespaces"
            />
          </section>
        </main>
        <aside
          class="settings__plan"
          aria-label="Plan"
          data-testid="hypertable-plan"
          :aria-busy="planning"
        >
          <strong>Plan</strong>
          <p
            v-if="missing"
            class="settings__note"
          >
            {{ missing }}
          </p>
          <p
            v-else-if="planFailed"
            class="settings__failure"
            role="alert"
          >
            {{ planFailed }}
          </p>
          <p
            v-else-if="planning && preview === null"
            class="settings__note"
          >
            Planning…
          </p>
          <template v-else-if="preview">
            <AppBanner
              v-if="preview.blocked"
              tone="warning"
              data-testid="hypertable-plan-summary"
            >
              {{ preview.summary }}
            </AppBanner>
            <p
              v-else
              data-testid="hypertable-plan-summary"
            >
              {{ preview.summary }}
            </p>
            <ul
              v-if="preview.items?.length"
              class="settings__steps"
            >
              <li
                v-for="(item, at) in preview.items"
                :key="at"
              >
                {{ item }}
              </li>
            </ul>
          </template>
        </aside>
      </div>
    </div>
    <template #actions>
      <span class="settings__status">Nothing changes until it is applied</span>
      <AppButton
        :label="applyLabel"
        :loading="running"
        :disable="!ready"
        data-testid="hypertable-apply"
        @click="apply"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.settings__waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: var(--dp-space-5);
}
.settings__body {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.7fr);
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}
.settings__form {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: var(--dp-space-3);
}
.settings__group {
  display: grid;
  gap: var(--dp-space-3);
  padding-bottom: var(--dp-space-4);
  margin-bottom: var(--dp-space-4);
  border-bottom: 1px solid var(--dp-border);
}
.settings__group:last-child {
  border-bottom: none;
}
.settings__pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-3);
}
.settings__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: var(--dp-space-3);
  align-items: center;
}
.settings__inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-2);
}
.settings__note {
  margin: 0;
  color: var(--dp-text-muted);
}
.settings__plan {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: var(--dp-space-3);
  background: var(--dp-chrome-raised);
  border-left: 1px solid var(--dp-border);
}
.settings__plan p {
  margin: var(--dp-space-2) 0;
}
.settings__steps {
  margin: 0;
  padding-left: var(--dp-space-4);
}
.settings__failure {
  color: var(--dp-content-error);
}
.settings__status {
  margin-right: auto;
  color: var(--dp-text-muted);
}
</style>
