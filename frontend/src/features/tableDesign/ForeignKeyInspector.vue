<script setup lang="ts">
import { computed } from "vue"

import { useSiblingTables } from "@/features/catalog/api"
import { AppBanner, AppCheckbox, AppInput, AppSelect } from "@/shared/ui"

import { useCandidateKeys, useDatabaseSchemas } from "./api"
import { useDesign } from "./design"
import type { DraftForeignKey } from "./draft"

const props = defineProps<{
  designId: string
  foreignKeyId: string
  connectorId: string
}>()

const design = useDesign(props.designId)

const foreign = computed<DraftForeignKey | undefined>(() =>
  design.draft.foreignKeys.find((item) => item.id === props.foreignKeyId)
)

/**
 * The target stays inside this connection.
 *
 * A physical foreign key is a promise the database keeps, so it can only point
 * at a table of the same database. A reference drawn between two sources is a
 * different feature with its own model (D106).
 */
const connector = computed(() => props.connectorId)
const schemas = useDatabaseSchemas(connector)
// Where the picker is looking, held on the draft rather than worked out from
// the target: a node id is the source's and is never taken apart here (D21).
const schemaId = computed(() => foreign.value?.targetSchemaId ?? "")
const tables = useSiblingTables(
  connector,
  computed(() => (schemaId.value === "" ? null : schemaId.value))
)
const targetId = computed(() => foreign.value?.targetNodeId ?? "")
const keys = useCandidateKeys(connector, targetId)

const schemaChoices = computed(() =>
  (schemas.data.value ?? []).map((node) => ({ label: node.name, value: node.id }))
)
const tableChoices = computed(() =>
  tables.value.map((node) => ({ label: node.name, value: node.id }))
)
/**
 * What the target says may be pointed at, spelled out.
 *
 * A key is picked whole rather than assembled: the value carries its columns
 * as written text, because that is what travels back, and a column name may
 * hold anything at all — including whatever character a shorter encoding
 * would have used as a separator.
 */
const keyChoices = computed(() =>
  (keys.data.value ?? []).map((key) => ({
    label: `${key.name} (${key.columns.join(", ")})`,
    value: JSON.stringify(key.columns),
  }))
)
const chosenKey = computed(() =>
  JSON.stringify(foreign.value?.targetColumns ?? [])
)

const actions = computed(() =>
  (design.options.value?.reference_actions ?? []).map((choice) => ({
    label: choice.title,
    value: choice.code,
  }))
)
const matches = computed(() =>
  (design.options.value?.match_modes ?? []).map((choice) => ({
    label: choice.title,
    value: choice.code,
  }))
)

const arity = computed(() => (foreign.value?.targetColumns ?? []).length)
const paired = computed(
  () => arity.value > 0 && (foreign.value?.columnIds ?? []).length === arity.value
)

function chooseSchema(nodeId: string): void {
  const held = foreign.value
  if (held === undefined) return
  held.targetSchemaId = nodeId
  // What it pointed at lived in the schema being left.
  held.targetNodeId = ""
  held.targetLabel = ""
  held.targetColumns = []
}

function chooseTable(nodeId: string): void {
  const held = foreign.value
  if (held === undefined) return
  held.targetNodeId = nodeId
  held.targetLabel = tableChoices.value.find((choice) => choice.value === nodeId)?.label ?? ""
  // The key it pointed at belonged to the old target.
  held.targetColumns = []
}

function chooseKey(value: string): void {
  const held = foreign.value
  if (held === undefined) return
  const chosen = keys.data.value?.find((key) => JSON.stringify(key.columns) === value)
  held.targetColumns = chosen === undefined ? [] : [...chosen.columns]
}
</script>

<template>
  <div
    v-if="foreign"
    class="inspector"
    data-testid="foreign-key-inspector"
  >
    <div class="inspector__row">
      <AppInput
        v-model="foreign.name"
        label="Name"
        hint="Left empty, the database names it"
      />
      <AppSelect
        v-model="foreign.columnIds"
        :options="design.columnChoices.value"
        label="Columns here"
        multiple
        data-testid="foreign-columns"
      />
    </div>

    <div class="inspector__row">
      <AppSelect
        :model-value="schemaId"
        :options="schemaChoices"
        label="Schema"
        :loading="schemas.isLoading.value"
        data-testid="foreign-schema"
        @update:model-value="chooseSchema(String($event))"
      />
      <AppSelect
        :model-value="foreign.targetNodeId"
        :options="tableChoices"
        label="Table"
        data-testid="foreign-table"
        @update:model-value="chooseTable(String($event))"
      />
      <AppSelect
        :model-value="chosenKey"
        :options="keyChoices"
        label="Key it points at"
        :loading="keys.isLoading.value"
        hint="What that table says may be pointed at"
        data-testid="foreign-key-columns"
        @update:model-value="chooseKey(String($event))"
      />
    </div>
    <AppBanner
      v-if="foreign.targetNodeId !== '' && keyChoices.length === 0 && !keys.isLoading.value"
      tone="warning"
    >
      That table publishes no key to point at.
    </AppBanner>
    <AppBanner
      v-else-if="arity > 0 && !paired"
      tone="warning"
    >
      A foreign key names as many columns as it points at:
      {{ arity }} {{ arity === 1 ? "column" : "columns" }} are expected here.
    </AppBanner>

    <div class="inspector__row">
      <AppSelect
        v-model="foreign.onUpdate"
        :options="actions"
        label="When it changes there"
      />
      <AppSelect
        v-model="foreign.onDelete"
        :options="actions"
        label="When it goes there"
        data-testid="foreign-on-delete"
      />
      <AppSelect
        v-model="foreign.match"
        :options="matches"
        label="Matching"
      />
    </div>

    <div class="inspector__row">
      <AppCheckbox
        v-model="foreign.deferrable"
        label="May be checked at the end of a transaction"
        dense
      />
      <AppCheckbox
        v-model="foreign.initiallyDeferred"
        label="Checked at the end by default"
        dense
        :disable="!foreign.deferrable"
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
  flex: 1 1 180px;
  min-width: 0;
}
</style>
