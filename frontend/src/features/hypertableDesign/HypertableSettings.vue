<script setup lang="ts">
import { computed, onBeforeUnmount, ref, toRef, watch } from "vue"

import type { ActionPreview, HypertableDesign } from "@/client"
import { usePreviewAction } from "@/features/catalog/api"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppForm,
  AppFormControl,
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
    planFailed.value = messageOf(cause, t("hypertable_design.plan_failed"))
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
  asJob.value
    ? t("hypertable_design.apply.start")
    : converting.value
      ? t("hypertable_design.apply.convert")
      : t("hypertable_design.apply.apply")
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
      title: t("hypertable_design.confirm.title"),
      message: job ? t("hypertable_design.confirm.job") : t("hypertable_design.confirm.instant"),
      confirmLabel: job ? t("hypertable_design.apply.start") : t("hypertable_design.apply.convert"),
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

const templates = computed(() =>
  (timeColumn.value?.now_templates ?? []).map((value: NowTemplate) => ({
    label: t(`hypertable_design.templates.${value}`),
    value,
  }))
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
    ...(current ? [] : [{ label: t("hypertable_design.none"), value: "none" }]),
    ...(current?.kind === "current"
      ? [
          {
            label: facts.value?.integer_now_name
              ? t("hypertable_design.keep_function", { name: facts.value.integer_now_name })
              : t("hypertable_design.keep_current_function"),
            value: "current",
          },
        ]
      : []),
    { label: t("hypertable_design.existing_function"), value: "existing" },
    ...(templates.value.length > 0 ? [{ label: t("hypertable_design.template_function"), value: "template" }] : []),
  ]
})
const ordinaryNote = computed(() => {
  const rows = facts.value?.row_estimate
  if (rows === null || rows === undefined) return t("hypertable_design.chunks.ordinary_unknown")
  return t("hypertable_design.chunks.ordinary_estimate", { n: rows.toLocaleString() }, rows)
})

const units = (list: readonly DurationUnit[] | undefined) =>
  (list ?? []).map((unit) => ({ label: t(`hypertable_design.units.${unit}`), value: unit }))
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
    ? [{ label: t("hypertable_design.chosen_by_timescale"), value: "default" }]
    : []),
  { label: t("hypertable_design.none"), value: "none" },
  { label: t("hypertable_design.these_columns"), value: "columns" },
])
const orderModes = computed(() => [
  ...(facts.value?.per_chunk_defaults === true || !enabledNow.value
    ? [{ label: t("hypertable_design.chosen_by_timescale"), value: "default" }]
    : []),
  { label: t("hypertable_design.these_columns"), value: "columns" },
])

function policyModes(current: string | undefined, olderThan: string) {
  return [
    { label: t("hypertable_design.none"), value: "none" },
    { label: olderThan, value: "older_than" },
    ...(current ? [{ label: t("hypertable_design.keep_policy", { current }), value: "current" }] : []),
  ]
}
const retentionModes = computed(() =>
  policyModes(facts.value?.retention?.description, t("hypertable_design.drop_older"))
)
const columnstorePolicyModes = computed(() =>
  policyModes(facts.value?.columnstore_policy?.description, t("hypertable_design.compress_older"))
)
const indexes = computed(() => [
  { label: t("hypertable_design.none"), value: "" },
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
const sparseKinds = computed(() => [
  { label: t("hypertable_design.sparse_kinds.minmax"), value: "minmax" },
  { label: t("hypertable_design.sparse_kinds.bloom"), value: "bloom" },
])
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
    :title="converting ? t('hypertable_design.title_convert', { name: nodeLabel }) : t('hypertable_design.title_settings', { name: nodeLabel })"
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
        {{ messageOf(state.error.value, t('hypertable_design.read_failed')) }}
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
          <AppForm layout="section">
            <section class="settings__group">
              <h3 class="dp-section-title settings__title">
                {{ t('hypertable_design.chunks.title') }}
              </h3>
              <template v-if="converting">
                <AppFormControl>
                  <p class="settings__note">
                    {{ ordinaryNote }}
                  </p>
                </AppFormControl>
                <AppSelect
                  :model-value="draft.timeColumn"
                  :options="timeColumns"
                  :label="t('hypertable_design.chunks.time_column')"
                  data-testid="time-column"
                  @update:model-value="chooseTime"
                />
              </template>
              <AppFormControl v-else>
                <p class="settings__note">
                  {{ t('hypertable_design.chunks.partitioned', { column: facts?.time_column ?? '', type: facts?.time_column_type ?? '' }) }}
                </p>
              </AppFormControl>
              <div class="settings__amount">
                <AppNumberInput
                  v-model="draft.chunkInterval.amount"
                  :label="integer ? t('hypertable_design.chunks.covers_values') : t('hypertable_design.chunks.covers')"
                  data-testid="chunk-interval-amount"
                />
                <AppSelect
                  v-if="!integer"
                  v-model="draft.chunkInterval.unit"
                  :options="intervalUnits"
                  :label="t('hypertable_design.chunks.unit')"
                  label-hidden
                  data-testid="chunk-interval-unit"
                />
              </div>
              <AppFormControl>
                <AppForm
                  v-if="draft.hash.length"
                  layout="grid"
                  class="settings__rows"
                >
                  <div
                    v-for="(item, at) in draft.hash"
                    :key="at"
                    class="settings__row settings__row--pair"
                    data-testid="hash-dimension"
                  >
                    <AppSelect
                      v-model="item.column"
                      :options="hashable"
                      :label="t('hypertable_design.chunks.hash_column')"
                      :disable="item.existing"
                    />
                    <AppNumberInput
                      v-model="item.partitions"
                      :label="t('hypertable_design.chunks.partitions')"
                    />
                    <span class="settings__cell">
                      <AppIconButton
                        v-if="!item.existing"
                        :icon="appIcons.deleteOutline"
                        :tooltip="t('hypertable_design.chunks.remove_hash')"
                        @click="draft.hash.splice(at, 1)"
                      />
                    </span>
                  </div>
                </AppForm>
                <div class="settings__inline">
                  <AppButton
                    variant="quiet"
                    :icon="appIcons.add"
                    :label="t('hypertable_design.chunks.hash_dimension')"
                    :disable="facts?.has_chunks === true"
                    data-testid="add-hash-dimension"
                    @click="addHash"
                  />
                  <span
                    v-if="facts?.has_chunks"
                    class="settings__note"
                  >{{ converting ? t('hypertable_design.chunks.only_empty_table') : t('hypertable_design.chunks.only_no_chunks') }}</span>
                </div>
              </AppFormControl>
            </section>

            <section class="settings__group">
              <h3 class="dp-section-title settings__title">
                {{ t('hypertable_design.columnstore.title') }}
              </h3>
              <AppFormControl>
                <AppToggle
                  v-model="draft.columnstore"
                  :label="t('hypertable_design.columnstore.enabled')"
                  data-testid="columnstore-enabled"
                />
                <p
                  v-if="facts?.compressed_chunks && draft.columnstore"
                  class="settings__note"
                >
                  {{ t('hypertable_design.columnstore.stays_on') }}
                </p>
              </AppFormControl>
              <template v-if="draft.columnstore">
                <AppRadioGroup
                  v-model="draft.segmentMode"
                  :options="segmentModes"
                  :label="t('hypertable_design.columnstore.segment_by')"
                  data-testid="segment-mode"
                />
                <AppSelect
                  v-if="draft.segmentMode === 'columns'"
                  v-model="draft.segmentColumns"
                  :options="orderable"
                  :label="t('hypertable_design.columnstore.segment_columns')"
                  multiple
                  data-testid="segment-columns"
                />
                <AppRadioGroup
                  v-model="draft.orderMode"
                  :options="orderModes"
                  :label="t('hypertable_design.columnstore.order_by')"
                  data-testid="order-mode"
                />
                <AppFormControl v-if="draft.orderMode === 'columns'">
                  <AppForm
                    v-if="draft.orderColumns.length"
                    layout="grid"
                    class="settings__rows"
                  >
                    <div
                      v-for="(key, at) in draft.orderColumns"
                      :key="at"
                      class="settings__row"
                      data-testid="order-column"
                    >
                      <AppSelect
                        v-model="key.column"
                        :options="orderable"
                        :label="t('hypertable_design.columnstore.column')"
                      />
                      <span class="settings__cell">
                        <AppCheckbox
                          v-model="key.descending"
                          :label="t('hypertable_design.columnstore.descending')"
                        />
                      </span>
                      <span class="settings__cell">
                        <AppCheckbox
                          v-model="key.nullsFirst"
                          :label="t('hypertable_design.columnstore.nulls_first')"
                        />
                      </span>
                      <span class="settings__cell">
                        <AppIconButton
                          :icon="appIcons.deleteOutline"
                          :tooltip="t('hypertable_design.columnstore.remove_order')"
                          @click="draft.orderColumns.splice(at, 1)"
                        />
                      </span>
                    </div>
                  </AppForm>
                  <div class="settings__inline">
                    <AppButton
                      variant="quiet"
                      :icon="appIcons.add"
                      :label="t('hypertable_design.columnstore.order_column')"
                      data-testid="add-order-column"
                      @click="addOrder"
                    />
                    <span class="settings__note">{{ t('hypertable_design.columnstore.time_last') }}</span>
                  </div>
                </AppFormControl>
                <template v-if="facts?.sparse_indexes_supported">
                  <AppRadioGroup
                    v-model="draft.sparseMode"
                    :options="segmentModes"
                    :label="t('hypertable_design.columnstore.sparse_indexes')"
                    data-testid="sparse-mode"
                  />
                  <AppFormControl v-if="draft.sparseMode === 'columns'">
                    <AppForm
                      v-if="draft.sparseIndexes.length"
                      layout="grid"
                      class="settings__rows"
                    >
                      <div
                        v-for="(item, at) in draft.sparseIndexes"
                        :key="at"
                        class="settings__row settings__row--pair"
                        data-testid="sparse-index"
                      >
                        <AppSelect
                          v-model="item.column"
                          :options="columns"
                          :label="t('hypertable_design.columnstore.column')"
                        />
                        <AppSelect
                          v-model="item.kind"
                          :options="sparseKinds"
                          :label="t('hypertable_design.columnstore.kind')"
                        />
                        <span class="settings__cell">
                          <AppIconButton
                            :icon="appIcons.deleteOutline"
                            :tooltip="t('hypertable_design.columnstore.remove_sparse')"
                            @click="draft.sparseIndexes.splice(at, 1)"
                          />
                        </span>
                      </div>
                    </AppForm>
                    <div class="settings__inline">
                      <AppButton
                        variant="quiet"
                        :icon="appIcons.add"
                        :label="t('hypertable_design.columnstore.sparse_index')"
                        data-testid="add-sparse-index"
                        @click="addSparse"
                      />
                      <span class="settings__note">{{ t('hypertable_design.columnstore.sparse_note') }}</span>
                    </div>
                  </AppFormControl>
                </template>
                <AppCheckbox
                  v-if="!integer"
                  v-model="draft.merge"
                  :label="t('hypertable_design.columnstore.merge')"
                  data-testid="merge-enabled"
                />
                <div
                  v-if="draft.merge && !integer"
                  class="settings__amount"
                >
                  <AppNumberInput
                    v-model="draft.mergeInterval.amount"
                    :label="t('hypertable_design.columnstore.merge_into')"
                    :hint="t('hypertable_design.columnstore.merge_hint')"
                    data-testid="merge-amount"
                  />
                  <AppSelect
                    v-model="draft.mergeInterval.unit"
                    :options="mergeUnits"
                    :label="t('hypertable_design.chunks.unit')"
                    label-hidden
                  />
                </div>
              </template>
            </section>

            <section
              v-if="integer"
              class="settings__group"
              data-testid="integer-now"
            >
              <h3 class="dp-section-title settings__title">
                {{ t('hypertable_design.now.title') }}
              </h3>
              <AppFormControl>
                <p class="settings__note">
                  {{ t('hypertable_design.now.note') }}
                </p>
              </AppFormControl>
              <AppSelect
                v-model="draft.now.mode"
                :options="nowModes"
                :label="t('hypertable_design.now.label')"
                data-testid="integer-now-mode"
              />
              <AppSelect
                v-if="draft.now.mode === 'existing'"
                v-model="draft.now.existing"
                :options="clocks"
                :label="t('hypertable_design.now.function')"
                :hint="t('hypertable_design.now.function_hint')"
                data-testid="integer-now-function"
              />
              <template v-if="draft.now.mode === 'template'">
                <AppSelect
                  v-model="draft.now.template"
                  :options="templates"
                  :label="t('hypertable_design.now.counts')"
                  data-testid="integer-now-template"
                />
                <AppInput
                  v-model="draft.now.name"
                  :label="t('hypertable_design.now.name')"
                  :hint="t('hypertable_design.now.name_hint', { schema: facts?.schema_name ?? '' })"
                  data-testid="integer-now-name"
                />
              </template>
            </section>

            <section class="settings__group">
              <h3 class="dp-section-title settings__title">
                {{ t('hypertable_design.policies.title') }}
              </h3>
              <AppSelect
                :model-value="draft.retention.mode"
                :options="retentionModes"
                :label="t('hypertable_design.policies.retention')"
                data-testid="retention-mode"
                @update:model-value="setPolicy('retention', String($event))"
              />
              <div
                v-if="draft.retention.mode === 'older_than'"
                class="settings__amount"
              >
                <AppNumberInput
                  v-model="draft.retention.duration.amount"
                  :label="integer ? t('hypertable_design.policies.age_values') : t('hypertable_design.policies.age')"
                  data-testid="retention-amount"
                />
                <AppSelect
                  v-if="!integer"
                  v-model="draft.retention.duration.unit"
                  :options="policyUnits"
                  :label="t('hypertable_design.chunks.unit')"
                  label-hidden
                />
              </div>
              <AppSelect
                :model-value="draft.columnstorePolicy.mode"
                :options="columnstorePolicyModes"
                :label="t('hypertable_design.policies.columnstore')"
                :disable="!draft.columnstore"
                data-testid="columnstore-policy-mode"
                @update:model-value="setPolicy('columnstorePolicy', String($event))"
              />
              <div
                v-if="draft.columnstorePolicy.mode === 'older_than'"
                class="settings__amount"
              >
                <AppNumberInput
                  v-model="draft.columnstorePolicy.duration.amount"
                  :label="integer ? t('hypertable_design.policies.age_values') : t('hypertable_design.policies.age')"
                  data-testid="columnstore-policy-amount"
                />
                <AppSelect
                  v-if="!integer"
                  v-model="draft.columnstorePolicy.duration.unit"
                  :options="policyUnits"
                  :label="t('hypertable_design.chunks.unit')"
                  label-hidden
                />
              </div>
              <AppCheckbox
                v-if="facts?.compaction_supported"
                v-model="draft.compaction"
                :label="t('hypertable_design.policies.compaction')"
                :disable="!draft.columnstore"
                data-testid="compaction-policy"
              />
              <AppSelect
                v-model="draft.reorderIndex"
                :options="indexes"
                :label="t('hypertable_design.policies.reorder')"
                :hint="facts?.reorder?.description"
                data-testid="reorder-index"
              />
            </section>

            <section class="settings__group">
              <h3 class="dp-section-title settings__title">
                {{ t('hypertable_design.tablespaces.title') }}
              </h3>
              <AppSelect
                v-model="draft.tablespaces"
                :options="tablespaces"
                :label="t('hypertable_design.tablespaces.new_chunks')"
                :hint="t('hypertable_design.tablespaces.hint')"
                multiple
                data-testid="tablespaces"
              />
            </section>
          </AppForm>
        </main>
        <aside
          class="settings__plan"
          :aria-label="t('hypertable_design.plan.title')"
          data-testid="hypertable-plan"
          :aria-busy="planning"
        >
          <strong>{{ t('hypertable_design.plan.title') }}</strong>
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
            {{ t('hypertable_design.plan.planning') }}
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
      <span class="settings__status">{{ t('hypertable_design.plan.nothing_until_applied') }}</span>
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
}
/* Quiet rules between regions (D131); the form's own gap spaces the fields. */
.settings__group {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-3);
  padding-bottom: var(--dp-space-4);
  border-bottom: 1px solid var(--dp-border);
}
.settings__group:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.settings__title {
  margin: 0;
}
/* A number and its unit on one line, the unit narrow beside it. */
.settings__amount {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 9rem;
  gap: var(--dp-space-2);
  align-items: start;
}
.settings__rows {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  margin-bottom: var(--dp-space-2);
}
/* Aligned on the controls rather than on the names above them, so a check
   box or a delete button stands level with the field it belongs to. */
.settings__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: var(--dp-space-3);
  align-items: end;
}
.settings__row--pair {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
}
.settings__cell {
  display: flex;
  align-items: center;
  min-height: var(--dp-form-control-height);
  min-width: var(--dp-form-control-height);
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
