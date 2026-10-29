<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import { t } from "@/shared/i18n"
import { AppButton, AppIconButton, AppInput, AppSelect, AppTooltip } from "@/shared/ui"

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
/** What is wrong with the draft, if anything. Apply stays blocked while there
    is an answer here, so an empty value can never be sent, and the answer is
    Apply's tooltip: the field is not marked before anything was typed. */
const problem = computed(() => validateDraft(draft.value))

function selectColumn(value: unknown) {
  if (typeof value !== "string") return
  const column = filterableColumns.value.find((candidate) => candidate.id === value)
  if (column === undefined) return
  draft.value = draftFor(column)
}

function selectOperator(value: unknown) {
  if (typeof value !== "string") return
  const op = operatorOptions(selectedColumn.value).find((candidate) => candidate === value)
  if (op === undefined) return
  draft.value = draftFor(selectedColumn.value, op as FilterOp)
}

function setValue(value: unknown) {
  if (typeof value !== "string") return
  draft.value.value = value
}

function addItem() {
  if (pendingItem.value.length === 0) return
  draft.value.values.push(pendingItem.value)
  pendingItem.value = ""
}

function addItemAndApply() {
  addItem()
  applyDraft()
}

function removeItem(index: number) {
  draft.value.values.splice(index, 1)
}

function applyDraft() {
  if (problem.value !== null) return
  emit("apply", [...props.filters, toFilter(draft.value)])
  draft.value = draftFor(selectedColumn.value)
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
          :icon="appIcons.close"
          :tooltip="t('grid.filter.delete', { n: index + 1 })"
          :data-testid="`grid-filter-delete-${index}`"
          @click="removeFilter(index)"
        />
      </div>
      <AppButton
        :label="t('grid.clear_all')"
        variant="quiet"
        size="sm"
        data-testid="grid-filter-clear"
        @click="emit('apply', [])"
      />
    </div>

    <div class="filter-editor__draft">
      <AppSelect
        class="filter-editor__field"
        :model-value="draft.column"
        :options="columnOptions"
        :label="t('grid.column')"
        compact
        @update:model-value="selectColumn"
      />
      <AppSelect
        class="filter-editor__field"
        :model-value="draft.op"
        :options="operatorSelectOptions"
        :label="t('grid.filter.operator')"
        compact
        @update:model-value="selectOperator"
      />

      <template v-if="draft.op === 'in'">
        <AppInput
          v-model="pendingItem"
          class="filter-editor__field"
          :label="t('grid.cell_editor.value')"
          compact
          @keyup.enter="addItemAndApply"
        />
        <AppButton
          :label="t('grid.add')"
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
        class="filter-editor__field"
        :model-value="draft.value"
        :options="explicitValueOptions"
        :label="t('grid.cell_editor.value')"
        compact
        @update:model-value="setValue"
      />
      <AppInput
        v-else-if="!isNullary"
        class="filter-editor__field"
        :model-value="draft.value"
        :label="t('grid.cell_editor.value')"
        compact
        data-testid="grid-filter-value"
        @update:model-value="setValue"
        @keyup.enter="applyDraft"
      />

      <!-- The tooltip hangs off this rather than off the button: a disabled
           Quasar button takes no pointer events, and why it waits is the one
           thing worth reading there. -->
      <span>
        <AppButton
          :label="t('grid.filter.apply')"
          size="sm"
          :disable="problem !== null"
          :aria-description="problem ?? undefined"
          data-testid="grid-filter-apply"
          @click="applyDraft"
        />
        <AppTooltip v-if="problem !== null">{{ problem }}</AppTooltip>
      </span>
    </div>
  </div>
</template>

<style scoped>
.filter-editor {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  min-height: calc(var(--dp-toolbar-height) + 2 * var(--dp-space-1));
  gap: var(--dp-space-2);
  padding: var(--dp-space-1) var(--dp-space-2);
  border-top: 1px solid var(--dp-border-faint);
}

.filter-editor__active,
.filter-editor__draft,
.filter-editor__condition {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.filter-editor__active,
.filter-editor__draft {
  flex-wrap: wrap;
}

.filter-editor__condition {
  padding-inline-start: var(--dp-space-2);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
}

.filter-editor__field {
  min-width: 140px;
}
</style>
