<script setup lang="ts">
import { computed, ref } from "vue"

import { AppButton, AppIconButton, AppInput, AppSelect } from "@/shared/ui"

import {
  describeFilter,
  draftFor,
  OPERATOR_LABELS,
  operatorOptions,
  toFilter,
  validateDraft,
} from "./filterModel"
import type { FilterDraft, FilterOp } from "./filterModel"
import type { TabularColumn } from "./tabular"
import type { Filter } from "./types"

const props = defineProps<{ columns: TabularColumn[]; filters: Filter[] }>()
const emit = defineEmits<{ apply: [filters: Filter[]]; close: [] }>()

const filterableColumns = computed(() =>
  props.columns.filter((column) => operatorOptions(column).length > 0)
)
const firstColumn = filterableColumns.value[0]
if (firstColumn === undefined) throw new Error("FilterEditor needs a filterable column")

const draft = ref<FilterDraft>(draftFor(firstColumn))
const error = ref("")
const pendingItem = ref("")

const selectedColumn = computed(() =>
  filterableColumns.value.find((column) => column.id === draft.value.column) ?? firstColumn
)
const columnOptions = computed(() =>
  filterableColumns.value.map((column) => ({ label: column.label, value: column.id }))
)
const operatorSelectOptions = computed(() =>
  operatorOptions(selectedColumn.value).map((op) => ({ label: OPERATOR_LABELS[op], value: op }))
)
const explicitValues = computed(() => {
  const type = selectedColumn.value.type
  if (type.category === "boolean") return ["true", "false"]
  if (type.category === "enum") return type.enum_values ?? []
  return null
})
const explicitValueOptions = computed(() =>
  (explicitValues.value ?? []).map((value) => ({ label: value, value }))
)
const isNullary = computed(
  () => draft.value.op === "is_null" || draft.value.op === "is_not_null"
)

function selectColumn(value: unknown) {
  if (typeof value !== "string") return
  const column = filterableColumns.value.find((candidate) => candidate.id === value)
  if (column === undefined) return
  draft.value = draftFor(column)
  error.value = ""
}

function selectOperator(value: unknown) {
  if (typeof value !== "string") return
  const op = operatorOptions(selectedColumn.value).find((candidate) => candidate === value)
  if (op === undefined) return
  draft.value = draftFor(selectedColumn.value, op as FilterOp)
  error.value = ""
}

function setValue(value: unknown) {
  if (typeof value === "string") draft.value.value = value
}

function addItem() {
  if (pendingItem.value.length === 0) return
  draft.value.values.push(pendingItem.value)
  pendingItem.value = ""
  error.value = ""
}

function addItemAndApply() {
  addItem()
  applyDraft()
}

function removeItem(index: number) {
  draft.value.values.splice(index, 1)
}

function applyDraft() {
  const validation = validateDraft(draft.value)
  if (validation !== null) {
    error.value = validation
    return
  }
  emit("apply", [...props.filters, toFilter(draft.value)])
  draft.value = draftFor(selectedColumn.value)
  error.value = ""
}

function removeFilter(index: number) {
  emit(
    "apply",
    props.filters.filter((_, filterIndex) => filterIndex !== index)
  )
}
</script>

<template>
  <div
    class="filter-editor"
    data-testid="grid-filter-editor"
    @keyup.esc="emit('close')"
  >
    <div
      v-if="filters.length > 0"
      class="filter-editor__active"
    >
      <div
        v-for="(filter, index) in filters"
        :key="`${filter.column}-${filter.op}-${index}`"
        class="filter-editor__condition"
      >
        <span>{{ describeFilter(filter) }}</span>
        <AppIconButton
          icon="close"
          :tooltip="`Delete filter ${index + 1}`"
          :data-testid="`grid-filter-delete-${index}`"
          @click="removeFilter(index)"
        />
      </div>
      <AppButton
        label="Clear all"
        variant="quiet"
        size="sm"
        data-testid="grid-filter-clear"
        @click="emit('apply', [])"
      />
    </div>

    <div class="filter-editor__draft">
      <AppSelect
        :model-value="draft.column"
        :options="columnOptions"
        label="Column"
        compact
        @update:model-value="selectColumn"
      />
      <AppSelect
        :model-value="draft.op"
        :options="operatorSelectOptions"
        label="Operator"
        compact
        @update:model-value="selectOperator"
      />

      <template v-if="draft.op === 'in'">
        <AppInput
          v-model="pendingItem"
          label="Value"
          compact
          @keyup.enter="addItemAndApply"
        />
        <AppButton
          label="Add"
          variant="quiet"
          size="sm"
          @click="addItem"
        />
        <q-chip
          v-for="(value, index) in draft.values"
          :key="`${value}-${index}`"
          removable
          @remove="removeItem(index)"
        >
          {{ value }}
        </q-chip>
      </template>
      <AppSelect
        v-else-if="!isNullary && explicitValues !== null"
        :model-value="draft.value"
        :options="explicitValueOptions"
        label="Value"
        compact
        @update:model-value="setValue"
      />
      <AppInput
        v-else-if="!isNullary"
        :model-value="draft.value"
        label="Value"
        compact
        data-testid="grid-filter-value"
        @update:model-value="setValue"
        @keyup.enter="applyDraft"
      />

      <AppButton
        label="Apply"
        size="sm"
        data-testid="grid-filter-apply"
        @click="applyDraft"
      />
      <span
        v-if="error"
        class="filter-editor__error"
      >
        {{ error }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.filter-editor {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  min-height: 48px;
  gap: 8px;
  padding: 4px 8px;
  border-top: 1px solid var(--dp-border-faint);
}

.filter-editor__active,
.filter-editor__draft,
.filter-editor__condition {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-editor__active,
.filter-editor__draft {
  flex-wrap: wrap;
}

.filter-editor__condition {
  padding-left: 8px;
  border: 1px solid var(--dp-border);
  border-radius: 4px;
}

.filter-editor__draft :deep(.q-field) {
  min-width: 140px;
}

.filter-editor__error {
  color: var(--q-negative);
  white-space: nowrap;
}
</style>
