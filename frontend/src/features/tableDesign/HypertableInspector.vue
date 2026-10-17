<script setup lang="ts">
import { computed, watch } from "vue"

import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppIconButton,
  AppInput,
  AppNumberInput,
  AppRadioGroup,
  AppSelect,
  AppToggle,
  appIcons,
} from "@/shared/ui"

import { t } from "@/shared/i18n"

import { useDesign } from "./design"
import { INTEGER_TIME_CODES, asHypertable, hypertableMissing, retimedHypertable } from "./draft"
import type { DraftAge, DurationUnit, NowTemplate } from "./draft"

const props = defineProps<{ designId: string }>()

const design = useDesign(props.designId)
const offer = computed(() => design.options.value?.hypertable ?? null)
const hyper = computed(() => design.draft.hypertable)
const missing = computed(() => hypertableMissing(design.draft.hypertable))

const units = (list: readonly DurationUnit[] | undefined) =>
  (list ?? []).map((unit) => ({ label: t(`hypertable_design.units.${unit}`), value: unit }))
const intervalUnits = computed(() => units(offer.value?.interval_units))
const policyUnits = computed(() => units(offer.value?.policy_units))

const integerTypes = computed(() => offer.value?.integer_types ?? [])
const temporal = computed(() =>
  design.draft.columns
    .filter(
      (column) =>
        column.dimensions === 0 &&
        (["timestamp_tz", "timestamp", "date"].includes(column.typeCode) ||
          (column.typeCode === "uuid" && offer.value?.uuid_time === true) ||
          (INTEGER_TIME_CODES.includes(column.typeCode) &&
            integerTypes.value.some((item) => item.type === column.typeCode)))
    )
    .map((column) => ({ label: column.name || t("table_design.unnamed"), value: column.id }))
)
const timeType = computed(
  () => design.draft.columns.find((column) => column.id === hyper.value?.timeColumnId)?.typeCode ?? ""
)
const integerType = computed(() => integerTypes.value.find((item) => item.type === timeType.value) ?? null)
/** Counted in the column's own values rather than in time (D207). */
const integer = computed(() => hyper.value?.intervalUnit === "integer")

// Another type of time column counts its lengths in another way, so the
// section takes what the server proposes for it. Immediate, because the type
// may have changed in the Columns section while this one was not shown.
watch(
  timeType,
  (type, before) => {
    const current = design.draft.hypertable
    if (current === null) return
    const mismatched = (integerType.value !== null) !== (current.intervalUnit === "integer")
    // One integer type for another proposes another interval and other templates.
    const otherInteger =
      before !== undefined && type !== before && INTEGER_TIME_CODES.includes(before) && INTEGER_TIME_CODES.includes(type)
    if (mismatched || otherInteger) {
      design.draft.hypertable = retimedHypertable(current, integerType.value)
    }
  },
  { immediate: true }
)

const templates = computed(() =>
  (integerType.value?.now_templates ?? []).map((value: NowTemplate) => ({
    label: t(`hypertable_design.templates.${value}`),
    value,
  }))
)
const clocks = computed(() =>
  (offer.value?.now_functions ?? [])
    .filter((item) => item.type === timeType.value)
    .map((item) => ({
      label: `${item.schema_name}.${item.name}()`,
      value: JSON.stringify([item.schema_name, item.name]),
    }))
)
const sparseModes = computed(() => [
  { label: t("hypertable_design.chosen_by_timescale"), value: "default" },
  { label: t("hypertable_design.none"), value: "none" },
  { label: t("hypertable_design.these_columns"), value: "columns" },
])
const sparseKinds = [
  { label: "minmax", value: "minmax" },
  { label: "bloom", value: "bloom" },
]

const nowModes = computed(() => [
  { label: t("hypertable_design.none"), value: "none" },
  { label: t("hypertable_design.existing_function"), value: "existing" },
  ...(templates.value.length > 0 ? [{ label: t("hypertable_design.template_function"), value: "template" }] : []),
])
const others = computed(() =>
  design.columnChoices.value.filter((choice) => choice.value !== hyper.value?.timeColumnId)
)
const indexes = computed(() => [
  { label: t("hypertable_design.none"), value: "" },
  ...design.draft.indexes.map((index) => ({ label: index.name || t("table_design.automatic_index_name"), value: index.id })),
])
const segmentModes = sparseModes
const orderModes = computed(() => [
  { label: t("hypertable_design.chosen_by_timescale"), value: "default" },
  { label: t("hypertable_design.these_columns"), value: "columns" },
])

function toggle(on: boolean) {
  if (!on) {
    design.draft.hypertable = null
    return
  }
  const method = design.options.value?.index_methods?.[0]?.code ?? "btree"
  Object.assign(design.draft, asHypertable(design.draft, method))
}

const ages = computed<{ key: string; label: string; age: DraftAge; disabled: boolean }[]>(() => {
  const current = hyper.value
  if (current === null) return []
  return [
    { key: "retention", label: t("hypertable_design.drop_older"), age: current.retention, disabled: false },
    {
      key: "columnstore-policy",
      label: t("hypertable_design.compress_older"),
      age: current.columnstorePolicy,
      disabled: !current.columnstore,
    },
  ]
})
</script>

<template>
  <div
    class="inspector"
    data-testid="hypertable-options"
  >
    <AppBanner
      v-if="offer && !offer.available"
      tone="info"
    >
      {{ offer.reason }}
    </AppBanner>
    <AppToggle
      :model-value="hyper !== null"
      :label="t('table_design.hypertable.create')"
      :disable="!offer?.available"
      data-testid="table-hypertable"
      @update:model-value="toggle"
    />
    <template v-if="hyper">
      <AppBanner
        v-if="missing"
        tone="warning"
      >
        {{ missing }}
      </AppBanner>
      <p class="inspector__note">
        {{ t('table_design.hypertable.note') }}
      </p>

      <section class="inspector__group">
        <AppSelect
          v-model="hyper.timeColumnId"
          :options="temporal"
          :label="t('hypertable_design.chunks.time_column')"
          data-testid="hypertable-time-column"
        />
        <div class="inspector__pair">
          <AppNumberInput
            v-model="hyper.intervalAmount"
            :label="integer ? t('hypertable_design.chunks.covers_values') : t('hypertable_design.chunks.covers')"
            data-testid="hypertable-interval"
          />
          <AppSelect
            v-if="!integer"
            v-model="hyper.intervalUnit"
            :options="intervalUnits"
            :label="t('hypertable_design.chunks.unit')"
          />
        </div>
        <div
          v-for="(item, at) in hyper.hash"
          :key="at"
          class="inspector__line inspector__line--pair"
        >
          <AppSelect
            v-model="item.columnId"
            :options="others"
            :label="t('hypertable_design.chunks.hash_column')"
          />
          <AppNumberInput
            v-model="item.partitions"
            :label="t('hypertable_design.chunks.partitions')"
          />
          <span class="inspector__cell">
            <AppIconButton
              :icon="appIcons.deleteOutline"
              :tooltip="t('hypertable_design.chunks.remove_hash')"
              @click="hyper.hash.splice(at, 1)"
            />
          </span>
        </div>
        <div>
          <AppButton
            variant="quiet"
            :icon="appIcons.add"
            :label="t('hypertable_design.chunks.hash_dimension')"
            @click="hyper.hash.push({ columnId: '', partitions: 4 })"
          />
        </div>
      </section>

      <section class="inspector__group">
        <AppToggle
          v-model="hyper.columnstore"
          :label="t('hypertable_design.columnstore.title')"
          data-testid="hypertable-columnstore"
        />
        <template v-if="hyper.columnstore">
          <AppRadioGroup
            v-model="hyper.segmentMode"
            :options="segmentModes"
            :label="t('hypertable_design.columnstore.segment_by')"
          />
          <AppSelect
            v-if="hyper.segmentMode === 'columns'"
            v-model="hyper.segmentColumnIds"
            :options="others"
            :label="t('hypertable_design.columnstore.segment_columns')"
            multiple
          />
          <AppRadioGroup
            v-model="hyper.orderMode"
            :options="orderModes"
            :label="t('hypertable_design.columnstore.order_by')"
          />
          <template v-if="hyper.orderMode === 'columns'">
            <div
              v-for="(key, at) in hyper.orderKeys"
              :key="at"
              class="inspector__line"
            >
              <AppSelect
                v-model="key.columnId"
                :options="design.columnChoices.value"
                :label="t('table_design.column_label')"
              />
              <span class="inspector__cell">
                <AppCheckbox
                  v-model="key.descending"
                  :label="t('hypertable_design.columnstore.descending')"
                />
              </span>
              <span class="inspector__cell">
                <AppCheckbox
                  v-model="key.nullsFirst"
                  :label="t('hypertable_design.columnstore.nulls_first')"
                />
              </span>
              <span class="inspector__cell">
                <AppIconButton
                  :icon="appIcons.deleteOutline"
                  :tooltip="t('hypertable_design.columnstore.remove_order')"
                  @click="hyper.orderKeys.splice(at, 1)"
                />
              </span>
            </div>
            <div>
              <AppButton
                variant="quiet"
                :icon="appIcons.add"
                :label="t('hypertable_design.columnstore.order_column')"
                @click="hyper.orderKeys.push({ columnId: '', descending: false, nullsFirst: false })"
              />
            </div>
          </template>
          <template v-if="offer?.sparse_indexes">
            <AppRadioGroup
              v-model="hyper.sparseMode"
              :options="sparseModes"
              :label="t('hypertable_design.columnstore.sparse_indexes')"
              data-testid="hypertable-sparse-mode"
            />
            <template v-if="hyper.sparseMode === 'columns'">
              <div
                v-for="(item, at) in hyper.sparseIndexes"
                :key="at"
                class="inspector__line inspector__line--pair"
              >
                <AppSelect
                  v-model="item.columnId"
                  :options="design.columnChoices.value"
                  :label="t('table_design.column_label')"
                />
                <AppSelect
                  v-model="item.kind"
                  :options="sparseKinds"
                  :label="t('hypertable_design.columnstore.kind')"
                />
                <span class="inspector__cell">
                  <AppIconButton
                    :icon="appIcons.deleteOutline"
                    :tooltip="t('hypertable_design.columnstore.remove_sparse')"
                    @click="hyper.sparseIndexes.splice(at, 1)"
                  />
                </span>
              </div>
              <div>
                <AppButton
                  variant="quiet"
                  :icon="appIcons.add"
                  :label="t('hypertable_design.columnstore.sparse_index')"
                  @click="hyper.sparseIndexes.push({ columnId: '', kind: 'minmax' })"
                />
              </div>
            </template>
          </template>
          <AppCheckbox
            v-if="!integer"
            v-model="hyper.merge.on"
            :label="t('hypertable_design.columnstore.merge')"
          />
          <div
            v-if="hyper.merge.on && !integer"
            class="inspector__pair"
          >
            <AppNumberInput
              v-model="hyper.merge.amount"
              :label="t('hypertable_design.columnstore.merge_into')"
            />
            <AppSelect
              v-model="hyper.merge.unit"
              :options="intervalUnits"
              :label="t('hypertable_design.chunks.unit')"
            />
          </div>
        </template>
      </section>

      <section
        v-if="integer"
        class="inspector__group"
      >
        <AppSelect
          v-model="hyper.now.mode"
          :options="nowModes"
          :label="t('hypertable_design.now.label')"
          :hint="t('table_design.hypertable.now_hint')"
          data-testid="hypertable-now-mode"
        />
        <AppSelect
          v-if="hyper.now.mode === 'existing'"
          v-model="hyper.now.existing"
          :options="clocks"
          :label="t('table_design.function')"
          data-testid="hypertable-now-function"
        />
        <div
          v-if="hyper.now.mode === 'template'"
          class="inspector__pair"
        >
          <AppSelect
            v-model="hyper.now.template"
            :options="templates"
            :label="t('hypertable_design.now.counts')"
            data-testid="hypertable-now-template"
          />
          <AppInput
            v-model="hyper.now.name"
            :label="t('hypertable_design.now.name')"
            :hint="t('table_design.hypertable.name_hint')"
            data-testid="hypertable-now-name"
          />
        </div>
      </section>

      <section class="inspector__group">
        <template
          v-for="item in ages"
          :key="item.key"
        >
          <AppCheckbox
            v-model="item.age.on"
            :label="item.label"
            :disable="item.disabled"
            :data-testid="`hypertable-${item.key}`"
          />
          <div
            v-if="item.age.on && !item.disabled"
            class="inspector__pair"
          >
            <AppNumberInput
              v-model="item.age.amount"
              :label="integer ? t('hypertable_design.policies.age_values') : t('hypertable_design.policies.age')"
              :data-testid="`hypertable-${item.key}-amount`"
            />
            <AppSelect
              v-if="!integer"
              v-model="item.age.unit"
              :options="policyUnits"
              :label="t('hypertable_design.chunks.unit')"
            />
          </div>
        </template>
        <AppCheckbox
          v-if="offer?.compaction"
          v-model="hyper.compaction"
          :label="t('hypertable_design.policies.compaction')"
          :disable="!hyper.columnstore"
          data-testid="hypertable-compaction"
        />
        <AppSelect
          v-model="hyper.reorderIndexId"
          :options="indexes"
          :label="t('table_design.hypertable.reorder')"
        />
      </section>
    </template>
  </div>
</template>

<style scoped>
.inspector {
  display: grid;
  gap: var(--dp-space-3);
}
/* Quiet rules between groups, the way D131 separates a window's regions. */
.inspector__group {
  display: grid;
  gap: var(--dp-space-3);
  padding-top: var(--dp-space-3);
  border-top: 1px solid var(--dp-border);
}
.inspector__pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-3);
  align-items: end;
}
/* Aligned on the controls rather than on the labels above them, so a check
   box or a delete button stands level with the field it belongs to. */
.inspector__line {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: var(--dp-space-3);
  align-items: end;
}
.inspector__line--pair {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
}
.inspector__cell {
  display: flex;
  align-items: center;
  min-height: var(--dp-form-control-height);
}
.inspector__note {
  margin: 0;
  color: var(--dp-text-muted);
}
@container table-designer (max-width: 560px) {
  .inspector__pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
