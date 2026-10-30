<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"
import { AppBanner, AppCheckbox, AppInput, AppNumberInput, AppSelect } from "@/shared/ui"

import { functionChoices, useDesign } from "./design"
import type { DraftColumn, DraftGeneration } from "./draft"

const props = defineProps<{ designId: string; columnId: string }>()

const design = useDesign(props.designId)

const column = computed<DraftColumn | undefined>(() =>
  design.draft.columns.find((item) => item.id === props.columnId)
)

const type = computed(() =>
  design.types.value.find((option) => option.code === column.value?.typeCode)
)
const takes = computed(() => type.value?.parameters ?? [])

const generationChoices = computed(() => {
  const choices = [
    { label: t("table_design.column.generation.none"), value: "none" },
    { label: t("table_design.column.generation.literal"), value: "literal" },
    { label: t("table_design.column.generation.expression"), value: "expression" },
    { label: t("table_design.column.generation.generated"), value: "generated" },
  ]
  // Only where the server says the type can carry one: PostgreSQL means
  // integers, and offering it on text would be offering a refusal.
  if (type.value?.identity_supported === true) {
    choices.splice(3, 0, { label: t("table_design.column.generation.identity"), value: "identity" })
  }
  return choices
})

const numberings = computed(() => [
  { label: t("table_design.column.always"), value: "always" },
  { label: t("table_design.column.by_default"), value: "by_default" },
])

const defaultFunctions = computed(() => functionChoices(design.functions.value, "default", 0))
const computedFunctions = computed(() => functionChoices(design.functions.value, "generated", 1))
const otherColumns = computed(() =>
  design.columnChoices.value.filter((choice) => choice.value !== props.columnId)
)
const collations = computed(() => [
  { label: "", value: "" },
  ...(design.options.value?.collations ?? []).map((name) => ({
    label: name,
    value: name,
  })),
])

const inKey = computed(() => design.draft.primaryKey.includes(props.columnId))

/** Which shape the generation takes, kept apart so switching keeps nothing. */
function changeGeneration(kind: string): void {
  const held = column.value
  if (held === undefined) return
  const chosen: Record<string, DraftGeneration> = {
    none: { kind: "none" },
    literal: { kind: "literal", value: "" },
    expression: { kind: "expression", function: "" },
    identity: {
      kind: "identity",
      generated: "by_default",
      start: null,
      increment: null,
    },
    generated: { kind: "generated", function: "", columnId: "" },
  }
  held.generation = chosen[kind] ?? { kind: "none" }
}

function changeKeyMembership(member: boolean): void {
  const key = design.draft.primaryKey
  const at = key.indexOf(props.columnId)
  if (member && at === -1) key.push(props.columnId)
  if (!member && at !== -1) key.splice(at, 1)
}
function changeDefault(value: string): void {
  const held = column.value
  if (!held || (held.generation.kind === "none" && value === "")) return
  held.generation = { kind: "literal", value }
}
</script>

<template>
  <div
    v-if="column"
    class="inspector"
    data-testid="column-inspector"
  >
    <div class="inspector__row">
      <AppInput
        v-model="column.name"
        :label="t('table_design.name')"
        data-testid="column-name"
      />
      <AppSelect
        v-model="column.typeCode"
        :options="design.typeChoices.value"
        :label="t('table_design.column.data_type')"
        data-testid="column-type"
      />
    </div>

    <div class="inspector__row">
      <AppSelect
        :model-value="column.generation.kind"
        :options="generationChoices"
        :label="t('table_design.column.value_generation')"
        data-testid="column-generation"
        @update:model-value="changeGeneration(String($event))"
      />
      <AppInput
        v-if="column.generation.kind === 'literal' || column.generation.kind === 'none'"
        :model-value="column.generation.kind === 'literal' ? column.generation.value : ''"
        :label="t('table_design.column.default_value')"
        data-testid="column-default"
        @update:model-value="changeDefault"
      />
      <AppSelect
        v-else-if="column.generation.kind === 'expression'"
        v-model="column.generation.function"
        :options="defaultFunctions"
        :label="t('table_design.function')"
        data-testid="column-default-function"
      />
      <template v-else-if="column.generation.kind === 'identity'">
        <AppSelect
          v-model="column.generation.generated"
          :options="numberings"
          :label="t('table_design.column.numbered')"
        />
        <AppNumberInput
          v-model="column.generation.start"
          :label="t('table_design.column.starting_at')"
          placeholder="1"
        />
        <AppNumberInput
          v-model="column.generation.increment"
          :label="t('table_design.column.step')"
          placeholder="1"
        />
      </template>
      <template v-else-if="column.generation.kind === 'generated'">
        <AppSelect
          v-model="column.generation.function"
          :options="computedFunctions"
          :label="t('table_design.function')"
        />
        <AppSelect
          v-model="column.generation.columnId"
          :options="otherColumns"
          :label="t('table_design.column.of_column')"
        />
      </template>
    </div>

    <div class="inspector__row">
      <AppCheckbox
        v-model="column.notNull"
        :label="t('table_design.column.not_null')"
        dense
        data-testid="column-not-null"
      />
      <AppCheckbox
        v-if="design.sorted.value || inKey"
        :model-value="inKey"
        :label="t('table_design.primary_key')"
        dense
        data-testid="column-in-key"
        @update:model-value="changeKeyMembership"
      />
    </div>
    <AppBanner
      v-if="inKey && !column.notNull && column.generation.kind !== 'identity'"
      tone="warning"
    >
      {{ t('table_design.column.key_needs_value') }}
    </AppBanner>
    <div
      v-if="collations.length > 1 || design.abilities.value.comments"
      class="inspector__row"
    >
      <AppSelect
        v-if="collations.length > 1"
        v-model="column.collation"
        :options="collations"
        :label="t('table_design.column.collation')"
      />
      <AppInput
        v-if="design.abilities.value.comments"
        v-model="column.comment"
        :label="t('table_design.comment')"
      />
    </div>
    <details
      v-if="takes.length || type?.array_supported"
      class="inspector__advanced dp-disclosure"
    >
      <summary>{{ t('table_design.column.type_parameters') }}</summary>
      <div class="inspector__row">
        <AppNumberInput
          v-if="takes.includes('length')"
          v-model="column.length"
          :label="t('table_design.column.length')"
          data-testid="column-length"
        />
        <AppNumberInput
          v-if="takes.includes('precision')"
          v-model="column.precision"
          :label="t('table_design.column.precision')"
        />
        <AppNumberInput
          v-if="takes.includes('scale')"
          v-model="column.scale"
          :label="t('table_design.column.scale')"
        />
        <AppCheckbox
          v-if="type?.array_supported"
          :model-value="column.dimensions > 0"
          :label="t('table_design.column.array')"
          dense
          @update:model-value="column.dimensions = $event ? 1 : 0"
        />
      </div>
    </details>
  </div>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-3);
}
.inspector__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-3);
  align-items: end;
}
.inspector__row > * {
  min-width: 0;
}
.inspector__advanced {
  border-top: 1px solid var(--dp-border);
  padding-top: var(--dp-space-2);
}
.inspector__advanced summary {
  margin-bottom: var(--dp-space-2);
}
@container table-designer (max-width: 560px) {
  .inspector__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
