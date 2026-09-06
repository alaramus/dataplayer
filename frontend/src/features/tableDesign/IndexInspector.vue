<script setup lang="ts">
import { computed } from "vue"

import { AppButton, AppCheckbox, AppIconButton, AppInput, AppSelect } from "@/shared/ui"

import { functionChoices, useDesign } from "./design"
import { newIndexKey } from "./draft"
import type { DraftIndex, DraftIndexKey } from "./draft"
import PredicateEditor from "./PredicateEditor.vue"

const props = defineProps<{ designId: string; indexId: string }>()

const design = useDesign(props.designId)

const index = computed<DraftIndex | undefined>(() =>
  design.draft.indexes.find((item) => item.id === props.indexId)
)

const methods = computed(() =>
  (design.options.value?.index_methods ?? []).map((method) => ({
    label: method.title,
    value: method.code,
  }))
)
const method = computed(() =>
  (design.options.value?.index_methods ?? []).find(
    (option) => option.code === index.value?.method
  )
)
const indexFunctions = computed(() =>
  functionChoices(design.functions.value, "index", 1)
)

/**
 * The operator classes for the method in use, in the server's own words.
 *
 * Filtered by method rather than shown whole: a class belongs to one access
 * method, and offering GIN's to a B-tree index is offering a refusal.
 */
const operatorClasses = computed(() => [
  { label: "The usual one", value: "" },
  ...(design.options.value?.operator_classes ?? [])
    .filter((option) => option.method === method.value?.sql)
    .map((option) => ({ label: option.title, value: option.code })),
])

// Whether this method can carry columns it does not sort by. Read off the
// options rather than decided here: which methods take INCLUDE is a fact about
// the server.
const carries = computed(() =>
  ["btree", "gist"].includes(index.value?.method ?? "")
)

const keyed = computed(
  () => new Set((index.value?.keys ?? []).map((key) => key.columnId))
)
const carriable = computed(() =>
  design.columnChoices.value.filter((choice) => !keyed.value.has(String(choice.value)))
)

function addKey(): void {
  const held = index.value
  if (held === undefined) return
  const first = design.draft.columns[0]
  held.keys.push(newIndexKey(first?.id ?? ""))
}

function removeKey(key: DraftIndexKey): void {
  const held = index.value
  if (held === undefined) return
  held.keys.splice(held.keys.indexOf(key), 1)
}

function moveKey(key: DraftIndexKey, by: number): void {
  const held = index.value
  if (held === undefined) return
  const at = held.keys.indexOf(key)
  const to = at + by
  if (to < 0 || to >= held.keys.length) return
  held.keys.splice(at, 1)
  held.keys.splice(to, 0, key)
}
</script>

<template>
  <div
    v-if="index"
    class="inspector"
    data-testid="index-inspector"
  >
    <div class="inspector__row">
      <AppInput
        v-model="index.name"
        label="Name"
        hint="Left empty, the database names it"
        data-testid="index-name"
      />
      <AppSelect
        v-model="index.method"
        :options="methods"
        label="Method"
        data-testid="index-method"
      />
      <AppCheckbox
        v-model="index.unique"
        label="Values may not repeat"
        dense
        :disable="method?.unique_supported === false"
        data-testid="index-unique"
      />
    </div>

    <div class="inspector__group">
      <div class="inspector__legend">
        <span>Keys, in order</span>
      </div>
      <div
        v-for="(key, at) in index.keys"
        :key="key.id"
        class="inspector__key"
      >
        <AppSelect
          v-model="key.kind"
          :data-testid="`index-key-kind-${String(at)}`"
          :options="[
            { label: 'Column', value: 'column' },
            { label: 'Function of a column', value: 'expression' },
          ]"
          aria-label="What is indexed"
          compact
        />
        <AppSelect
          v-if="key.kind === 'expression'"
          v-model="key.function"
          :options="indexFunctions"
          aria-label="Function"
          compact
        />
        <AppSelect
          v-model="key.columnId"
          :options="design.columnChoices.value"
          aria-label="Column"
          compact
          :data-testid="`index-key-column-${String(at)}`"
        />
        <AppSelect
          v-model="key.direction"
          :options="[
            { label: 'Default order', value: '' },
            { label: 'Ascending', value: 'asc' },
            { label: 'Descending', value: 'desc' },
          ]"
          aria-label="Order"
          compact
        />
        <AppSelect
          v-model="key.nulls"
          :options="[
            { label: 'Empty values as usual', value: '' },
            { label: 'Empty values first', value: 'first' },
            { label: 'Empty values last', value: 'last' },
          ]"
          aria-label="Where empty values sit"
          compact
        />
        <AppSelect
          v-model="key.operatorClass"
          :options="operatorClasses"
          aria-label="Operator class"
          compact
        />
        <AppIconButton
          icon="arrow_upward"
          tooltip="Earlier in the key"
          compact
          :disable="at === 0"
          @click="moveKey(key, -1)"
        />
        <AppIconButton
          icon="close"
          tooltip="Remove this key"
          compact
          :disable="index.keys.length === 1"
          @click="removeKey(key)"
        />
      </div>
      <AppButton
        variant="quiet"
        size="sm"
        label="Add a key"
        data-testid="index-add-key"
        @click="addKey"
      />
    </div>

    <AppSelect
      v-if="carries"
      v-model="index.includeColumnIds"
      :options="carriable"
      label="Also carries"
      hint="Read from the index without sorting by it"
      multiple
    />

    <div class="inspector__group">
      <div class="inspector__legend">
        <span>Only rows where</span>
      </div>
      <PredicateEditor
        :design-id="designId"
        owner="index"
        :owner-id="index.id"
        testid="index-predicate"
      />
    </div>
  </div>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}

.inspector__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
  align-items: center;
}

.inspector__row > * {
  flex: 1 1 160px;
  min-width: 0;
}

.inspector__group {
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  padding: var(--dp-space-2);
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}

.inspector__legend {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dp-text-muted);
}

.inspector__key {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr)) auto auto;
  gap: var(--dp-space-1);
  align-items: center;
}
</style>
