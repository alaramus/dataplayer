<script setup lang="ts">
import { computed } from "vue"

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

const operators = [
  { label: "is", value: "eq" },
  { label: "is not", value: "ne" },
  { label: "is less than", value: "lt" },
  { label: "is at most", value: "lte" },
  { label: "is greater than", value: "gt" },
  { label: "is at least", value: "gte" },
  { label: "is one of", value: "in" },
  { label: "is none of", value: "not_in" },
  { label: "is empty", value: "is_null" },
  { label: "is not empty", value: "is_not_null" },
]

const kinds = [
  { label: "Text", value: "text" },
  { label: "Number", value: "number" },
  { label: "True or false", value: "boolean" },
  { label: "JSON", value: "json" },
]

const joins = [
  { label: "All of these", value: "and" },
  { label: "Any of these", value: "or" },
]

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
        label="Holds when"
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
        aria-label="Column"
        compact
      />
      <AppSelect
        v-model="term.operator"
        :options="operators"
        aria-label="Comparison"
        compact
      />
      <AppSelect
        v-if="takesValue(term)"
        v-model="term.valueKind"
        :options="kinds"
        aria-label="Kind of value"
        compact
      />
      <template v-if="takesValue(term) && !takesList(term)">
        <AppInput
          v-model="term.value"
          aria-label="Value"
          placeholder="Value"
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
            aria-label="Value"
            placeholder="Value"
            compact
            @update:model-value="term.values[index] = $event"
          />
          <AppIconButton
            icon="close"
            tooltip="Remove this value"
            compact
            :disable="term.values.length === 1"
            @click="term.values.splice(index, 1)"
          />
        </div>
        <AppButton
          variant="quiet"
          size="sm"
          label="Add a value"
          @click="term.values.push('')"
        />
      </div>
      <span v-else />
      <AppIconButton
        icon="close"
        tooltip="Remove this condition"
        compact
        @click="remove(term)"
      />
    </div>
    <AppButton
      variant="quiet"
      size="sm"
      label="Add a condition"
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
  grid-template-columns:
    minmax(90px, 1fr) minmax(90px, 1fr) minmax(80px, 0.8fr)
    minmax(120px, 1.4fr) auto;
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
</style>
