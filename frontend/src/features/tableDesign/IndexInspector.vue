<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { AppButton, AppCheckbox, AppIconButton, AppInput, AppSelect } from "@/shared/ui"

import { functionChoices, useDesign } from "./design"
import { newIndexKey } from "./draft"
import type { DraftIndex, DraftIndexKey } from "./draft"
import PredicateField from "./PredicateField.vue"

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
  (design.options.value?.index_methods ?? []).find((option) => option.code === index.value?.method)
)
const indexFunctions = computed(() => functionChoices(design.functions.value, "index", 1))

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
const carries = computed(() => ["btree", "gist"].includes(index.value?.method ?? ""))

const keyed = computed(() => new Set((index.value?.keys ?? []).map((key) => key.columnId)))
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
function include(columnId: string, checked: boolean): void {
  const held = index.value
  if (!held) return
  held.includeColumnIds = checked
    ? [...held.includeColumnIds, columnId]
    : held.includeColumnIds.filter((id) => id !== columnId)
}
</script>

<template>
  <div
    v-if="index"
    class="inspector"
    data-testid="index-inspector"
  >
    <AppInput
      v-model="index.name"
      label="Index name"
      placeholder="Automatic name"
      data-testid="index-name"
    />
    <div class="inspector__row">
      <AppSelect
        v-model="index.method"
        :options="methods"
        label="Access method"
        data-testid="index-method"
      />
      <AppCheckbox
        v-model="index.unique"
        label="Unique"
        dense
        :disable="method?.unique_supported === false"
        data-testid="index-unique"
      />
    </div>
    <div class="inspector__legend">
      <h3 class="dp-overline">
        Index keys · in order
      </h3>
      <AppButton
        variant="quiet"
        :icon="appIcons.add"
        label="Key"
        data-testid="index-add-key"
        @click="addKey"
      />
    </div>
    <div
      v-for="(key, at) in index.keys"
      :key="key.id"
      class="inspector__key"
    >
      <AppSelect
        v-model="key.columnId"
        :options="design.columnChoices.value"
        label="Column"
        :data-testid="`index-key-column-${String(at)}`"
      />
      <AppSelect
        v-model="key.direction"
        :options="[
          { label: 'Default', value: '' },
          { label: 'ASC', value: 'asc' },
          { label: 'DESC', value: 'desc' },
        ]"
        label="Order"
      />
      <AppSelect
        v-model="key.nulls"
        :options="[
          { label: 'Default', value: '' },
          { label: 'FIRST', value: 'first' },
          { label: 'LAST', value: 'last' },
        ]"
        label="Nulls"
      />
      <AppIconButton
        :icon="appIcons.close"
        :tooltip="`Remove index key ${at + 1}`"
        compact
        :disable="index.keys.length === 1"
        @click="removeKey(key)"
      />
    </div>
    <PredicateField
      :design-id="designId"
      owner="index"
      :owner-id="index.id"
      testid="index-predicate"
      label="Partial index · WHERE"
    />
    <template v-if="carries">
      <h3 class="dp-overline">
        Included columns · INCLUDE
      </h3>
      <div class="inspector__badges">
        <AppCheckbox
          v-for="choice in carriable"
          :key="choice.value"
          :model-value="index.includeColumnIds.includes(String(choice.value))"
          :label="choice.label"
          dense
          @update:model-value="include(String(choice.value), $event)"
        />
      </div>
    </template>
    <details class="inspector__advanced">
      <summary>Expression &amp; operator class</summary>
      <div
        v-for="(key, at) in index.keys"
        :key="key.id"
        class="inspector__advanced-key"
      >
        <h3 class="dp-overline">
          Key {{ at + 1 }}
        </h3>
        <div class="inspector__row">
          <AppSelect
            v-model="key.kind"
            :data-testid="`index-key-kind-${String(at)}`"
            :options="[
              { label: 'Column', value: 'column' },
              { label: 'Function of a column', value: 'expression' },
            ]"
            label="Expression"
          />
          <AppSelect
            v-if="key.kind === 'expression'"
            v-model="key.function"
            :options="indexFunctions"
            label="Function"
          />
          <AppSelect
            v-model="key.operatorClass"
            :options="operatorClasses"
            label="Operator class · optional"
          />
        </div>
        <AppButton
          variant="quiet"
          :icon="appIcons.arrowUpward"
          label="Move key up"
          :disable="at === 0"
          @click="moveKey(key, -1)"
        />
      </div>
    </details>
  </div>
  <p
    v-else
    class="inspector__note"
  >
    No additional indexes.
  </p>
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
.inspector__legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-2);
  margin-top: var(--dp-space-half);
}
.inspector h3 {
  margin: 0;
}
/* The column takes the room that is left; Order and Nulls keep a fixed width
   their choices ("Default") fit into, so the row never clips them. */
.inspector__key {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) 104px 104px 26px;
  gap: var(--dp-space-2);
  align-items: end;
}
.inspector__predicate {
  display: grid;
  gap: var(--dp-space-2);
}
.inspector__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
}
.inspector__badges > * {
  border: 1px solid var(--dp-border);
  padding: var(--dp-space-half) var(--dp-space-2);
  border-radius: var(--dp-radius-control);
}
.inspector__advanced {
  border-top: 1px solid var(--dp-border);
  padding-top: var(--dp-space-2);
}
.inspector__advanced summary {
  cursor: pointer;
  color: var(--dp-text-muted);
}
.inspector__advanced-key {
  display: grid;
  gap: var(--dp-space-3);
  margin-top: var(--dp-space-3);
}
.inspector__note {
  color: var(--dp-text-muted);
}
@container table-designer (max-width: 560px) {
  .inspector__row {
    grid-template-columns: minmax(0, 1fr);
  }
  .inspector__key {
    grid-template-columns: repeat(2, minmax(0, 1fr)) 26px;
  }
  .inspector__key > :first-child {
    grid-column: 1 / -1;
  }
}
</style>
