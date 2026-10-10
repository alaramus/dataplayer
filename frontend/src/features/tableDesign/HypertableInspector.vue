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

import { useDesign } from "./design"
import { INTEGER_TIME_CODES, asHypertable, hypertableMissing, retimedHypertable } from "./draft"
import type { DraftAge, DurationUnit, LengthUnit, NowTemplate } from "./draft"

const props = defineProps<{ designId: string }>()

const design = useDesign(props.designId)
const offer = computed(() => design.options.value?.hypertable ?? null)
const hyper = computed(() => design.draft.hypertable)
const missing = computed(() => hypertableMissing(design.draft.hypertable))

const UNIT_LABELS: Record<LengthUnit, string> = {
  integer: "values",
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
    .map((column) => ({ label: column.name || "(unnamed)", value: column.id }))
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

const TEMPLATE_LABELS: Record<NowTemplate, string> = {
  epoch_seconds: "Seconds since 1970",
  epoch_milliseconds: "Milliseconds since 1970",
  epoch_microseconds: "Microseconds since 1970",
}
const templates = computed(() =>
  (integerType.value?.now_templates ?? []).map((value) => ({ label: TEMPLATE_LABELS[value], value }))
)
const clocks = computed(() =>
  (offer.value?.now_functions ?? [])
    .filter((item) => item.type === timeType.value)
    .map((item) => ({
      label: `${item.schema_name}.${item.name}()`,
      value: JSON.stringify([item.schema_name, item.name]),
    }))
)
const sparseModes = [
  { label: "Chosen by TimescaleDB", value: "default" },
  { label: "None", value: "none" },
  { label: "These columns", value: "columns" },
]
const sparseKinds = [
  { label: "minmax", value: "minmax" },
  { label: "bloom", value: "bloom" },
]

const nowModes = computed(() => [
  { label: "None", value: "none" },
  { label: "A function of this database", value: "existing" },
  ...(templates.value.length > 0 ? [{ label: "A new function from a template", value: "template" }] : []),
])
const others = computed(() =>
  design.columnChoices.value.filter((choice) => choice.value !== hyper.value?.timeColumnId)
)
const indexes = computed(() => [
  { label: "None", value: "" },
  ...design.draft.indexes.map((index) => ({ label: index.name || "Automatic index name", value: index.id })),
])
const segmentModes = [
  { label: "Chosen by TimescaleDB", value: "default" },
  { label: "None", value: "none" },
  { label: "These columns", value: "columns" },
]
const orderModes = [
  { label: "Chosen by TimescaleDB", value: "default" },
  { label: "These columns", value: "columns" },
]

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
    { key: "retention", label: "Drop chunks older than", age: current.retention, disabled: false },
    {
      key: "columnstore-policy",
      label: "Compress chunks older than",
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
      label="Create as a hypertable"
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
        TimescaleDB adds no index of its own: the time index, newest first, is one of the table's
        indexes and can be removed like any other. Keys must hold the time column and every hash
        column.
      </p>
      <div class="inspector__row">
        <AppSelect
          v-model="hyper.timeColumnId"
          :options="temporal"
          label="Time column"
          data-testid="hypertable-time-column"
        />
        <div class="inspector__pair">
          <AppNumberInput
            v-model="hyper.intervalAmount"
            :label="integer ? 'Each chunk covers, in values' : 'Each chunk covers'"
            data-testid="hypertable-interval"
          />
          <AppSelect
            v-if="!integer"
            v-model="hyper.intervalUnit"
            :options="intervalUnits"
            label="Unit"
          />
        </div>
      </div>
      <div
        v-for="(item, at) in hyper.hash"
        :key="at"
        class="inspector__line"
      >
        <AppSelect
          v-model="item.columnId"
          :options="others"
          label="Hash column"
        />
        <AppNumberInput
          v-model="item.partitions"
          label="Partitions"
        />
        <AppIconButton
          :icon="appIcons.deleteOutline"
          tooltip="Remove this hash dimension"
          @click="hyper.hash.splice(at, 1)"
        />
      </div>
      <div>
        <AppButton
          variant="quiet"
          :icon="appIcons.add"
          label="Hash dimension"
          @click="hyper.hash.push({ columnId: '', partitions: 4 })"
        />
      </div>

      <AppToggle
        v-model="hyper.columnstore"
        label="Columnstore"
        data-testid="hypertable-columnstore"
      />
      <template v-if="hyper.columnstore">
        <AppRadioGroup
          v-model="hyper.segmentMode"
          :options="segmentModes"
          label="Segment by"
        />
        <AppSelect
          v-if="hyper.segmentMode === 'columns'"
          v-model="hyper.segmentColumnIds"
          :options="others"
          label="Segment columns"
          multiple
        />
        <AppRadioGroup
          v-model="hyper.orderMode"
          :options="orderModes"
          label="Order by"
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
              @click="hyper.orderKeys.splice(at, 1)"
            />
          </div>
          <div>
            <AppButton
              variant="quiet"
              :icon="appIcons.add"
              label="Order column"
              @click="hyper.orderKeys.push({ columnId: '', descending: false, nullsFirst: false })"
            />
          </div>
        </template>
        <template v-if="offer?.sparse_indexes">
          <AppRadioGroup
            v-model="hyper.sparseMode"
            :options="sparseModes"
            label="Sparse indexes"
            data-testid="hypertable-sparse-mode"
          />
          <template v-if="hyper.sparseMode === 'columns'">
            <div
              v-for="(item, at) in hyper.sparseIndexes"
              :key="at"
              class="inspector__line"
            >
              <AppSelect
                v-model="item.columnId"
                :options="design.columnChoices.value"
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
                @click="hyper.sparseIndexes.splice(at, 1)"
              />
            </div>
            <div>
              <AppButton
                variant="quiet"
                :icon="appIcons.add"
                label="Sparse index"
                @click="hyper.sparseIndexes.push({ columnId: '', kind: 'minmax' })"
              />
            </div>
          </template>
        </template>
        <AppCheckbox
          v-if="offer?.compaction"
          v-model="hyper.compaction"
          label="Compaction policy: merge small compressed chunks"
          data-testid="hypertable-compaction"
        />
        <AppCheckbox
          v-if="!integer"
          v-model="hyper.merge.on"
          label="Merge chunks as they are compressed"
        />
        <div
          v-if="hyper.merge.on && !integer"
          class="inspector__pair"
        >
          <AppNumberInput
            v-model="hyper.merge.amount"
            label="Into chunks of"
          />
          <AppSelect
            v-model="hyper.merge.unit"
            :options="intervalUnits"
            label="Unit"
          />
        </div>
      </template>

      <template v-if="integer">
        <AppSelect
          v-model="hyper.now.mode"
          :options="nowModes"
          label="integer_now"
          hint="Age policies on an integer column need a function that says what the current value is"
          data-testid="hypertable-now-mode"
        />
        <AppSelect
          v-if="hyper.now.mode === 'existing'"
          v-model="hyper.now.existing"
          :options="clocks"
          label="Function"
          data-testid="hypertable-now-function"
        />
        <div
          v-if="hyper.now.mode === 'template'"
          class="inspector__pair"
        >
          <AppSelect
            v-model="hyper.now.template"
            :options="templates"
            label="Counts"
            data-testid="hypertable-now-template"
          />
          <AppInput
            v-model="hyper.now.name"
            label="Function name"
            hint="Created in the table's schema"
            data-testid="hypertable-now-name"
          />
        </div>
      </template>
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
            :label="integer ? 'Age, in values' : 'Age'"
            :data-testid="`hypertable-${item.key}-amount`"
          />
          <AppSelect
            v-if="!integer"
            v-model="item.age.unit"
            :options="policyUnits"
            label="Unit"
          />
        </div>
      </template>
      <AppSelect
        v-model="hyper.reorderIndexId"
        :options="indexes"
        label="Reorder chunks by index"
      />
    </template>
  </div>
</template>

<style scoped>
.inspector {
  display: grid;
  gap: var(--dp-space-3);
}
.inspector__row,
.inspector__pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-3);
  align-items: start;
}
.inspector__line {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: var(--dp-space-3);
  align-items: center;
}
.inspector__note {
  margin: 0;
  color: var(--dp-text-muted);
}
@container table-designer (max-width: 560px) {
  .inspector__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
