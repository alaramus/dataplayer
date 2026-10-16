<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { t } from "@/shared/i18n"
import { AppButton, AppIconButton, AppInput, AppSelect } from "@/shared/ui"

import { useDesign } from "./design"
import { newTerm } from "./draft"
import type { DraftPredicate, DraftTerm } from "./draft"

/**
 * A condition, built out of terms rather than typed as SQL.
 *
 * The vocabulary is the model's: a column, one of a closed set of operators,
 * and a typed literal (D117). There is no field here that could hold a
 * fragment of a statement, which is the whole reason this is a row of selects
 * and not a text box.
 *
 * It is given the object that owns the condition rather than the condition
 * itself: what it edits then belongs to the shared draft, and editing a prop
 * in place — which is what a nested v-model would do — never arises.
 */
const props = defineProps<{
  designId: string
  owner: "index" | "check"
  ownerId: string
  testid: string
}>()

const design = useDesign(props.designId)

const predicate = computed<DraftPredicate>(() => {
  const held =
    props.owner === "index"
      ? design.draft.indexes.find((index) => index.id === props.ownerId)?.predicate
      : design.draft.checks.find((check) => check.id === props.ownerId)?.predicate
  return held ?? { operator: "and", terms: [] }
})

const OPERATORS: DraftTerm["operator"][] = [
  "eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "is_null", "is_not_null",
]
const operators = computed(() =>
  OPERATORS.map((value) => ({ label: t(`table_design.predicate.operators.${value}`), value }))
)

const KINDS: DraftTerm["valueKind"][] = ["text", "number", "boolean", "json"]
const kinds = computed(() =>
  KINDS.map((value) => ({ label: t(`table_design.predicate.kinds.${value}`), value }))
)

const joins = computed(() => [
  { label: t("table_design.predicate.joins.and"), value: "and" },
  { label: t("table_design.predicate.joins.or"), value: "or" },
])

const terms = computed(() => predicate.value.terms)

function add(): void {
  const first = design.draft.columns[0]
  predicate.value.terms.push(newTerm(first?.id ?? ""))
}

function remove(term: DraftTerm): void {
  predicate.value.terms.splice(predicate.value.terms.indexOf(term), 1)
}

function takesValue(term: DraftTerm): boolean {
  return term.operator !== "is_null" && term.operator !== "is_not_null"
}

function takesList(term: DraftTerm): boolean {
  return term.operator === "in" || term.operator === "not_in"
}
</script>

<template>
  <div
    class="predicate"
    :data-testid="testid"
  >
    <div
      v-if="terms.length > 1"
      class="predicate__join"
    >
      <AppSelect
        v-model="predicate.operator"
        :options="joins"
        :label="t('table_design.predicate.holds_when')"
        compact
        :data-testid="`${testid}-join`"
      />
    </div>
    <div
      v-for="(term, at) in terms"
      :key="term.id"
      class="predicate__term"
      :data-testid="`${testid}-term-${String(at)}`"
    >
      <AppSelect
        v-model="term.columnId"
        :options="design.columnChoices.value"
        :aria-label="t('table_design.column_label')"
        compact
      />
      <AppSelect
        v-model="term.operator"
        :options="operators"
        :aria-label="t('table_design.predicate.comparison')"
        compact
      />
      <AppSelect
        v-if="takesValue(term)"
        v-model="term.valueKind"
        :options="kinds"
        :aria-label="t('table_design.predicate.kind')"
        compact
      />
      <template v-if="takesValue(term) && !takesList(term)">
        <AppInput
          v-model="term.value"
          :aria-label="t('table_design.predicate.value')"
          :placeholder="t('table_design.predicate.value')"
          compact
        />
      </template>
      <div
        v-else-if="takesList(term)"
        class="predicate__values"
      >
        <div
          v-for="(_, index) in term.values"
          :key="index"
          class="predicate__value"
        >
          <AppInput
            :model-value="term.values[index] ?? ''"
            :aria-label="t('table_design.predicate.value')"
            :placeholder="t('table_design.predicate.value')"
            compact
            @update:model-value="term.values[index] = $event"
          />
          <AppIconButton
            :icon="appIcons.close"
            :tooltip="t('table_design.predicate.remove_value')"
            compact
            :disable="term.values.length === 1"
            @click="term.values.splice(index, 1)"
          />
        </div>
        <AppButton
          variant="quiet"
          size="sm"
          :label="t('table_design.predicate.add_value')"
          @click="term.values.push('')"
        />
      </div>
      <span v-else />
      <AppIconButton
        :icon="appIcons.close"
        :tooltip="t('table_design.predicate.remove_condition')"
        compact
        @click="remove(term)"
      />
    </div>
    <AppButton
      variant="quiet"
      size="sm"
      :label="t('table_design.predicate.add_condition')"
      :data-testid="`${testid}-add`"
      @click="add"
    />
  </div>
</template>

<style scoped>
.predicate {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}

/* One condition to a row, and its parts in the order they are read: the
   column, the comparison, what kind of value, then the value itself. A list
   of values grows downwards inside its own cell rather than widening the
   row. */
.predicate__term {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: var(--dp-space-1);
  align-items: start;
}

.predicate__join {
  max-width: 180px;
}

.predicate__values {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  align-items: flex-start;
}

.predicate__value {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: var(--dp-space-1);
  width: 100%;
}
.predicate__term > :nth-child(3),
.predicate__term > :nth-child(4) {
  grid-row: 2;
}
.predicate__term > :last-child {
  grid-column: 3;
  grid-row: 1;
}
.predicate__values {
  min-width: 0;
}
</style>
