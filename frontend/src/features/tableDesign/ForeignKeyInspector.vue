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
const chosenKey = computed(() => JSON.stringify(foreign.value?.targetColumns ?? []))

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
  held.columnIds = held.targetColumns.map((_, at) => held.columnIds[at] ?? "")
}
</script>

<template>
  <div
    v-if="foreign"
    class="inspector"
    data-testid="foreign-key-inspector"
  >
    <AppInput
      v-model="foreign.name"
      label="Constraint name"
      placeholder="Automatic name"
    />
    <div class="inspector__row">
      <AppSelect
        :model-value="schemaId"
        :options="schemaChoices"
        label="Referenced schema"
        :loading="schemas.isLoading.value"
        data-testid="foreign-schema"
        @update:model-value="chooseSchema(String($event))"
      />
      <AppSelect
        :model-value="foreign.targetNodeId"
        :options="tableChoices"
        label="Referenced table"
        data-testid="foreign-table"
        @update:model-value="chooseTable(String($event))"
      />
      <AppSelect
        :model-value="chosenKey"
        :options="keyChoices"
        label="Referenced key"
        :loading="keys.isLoading.value"
        data-testid="foreign-key-columns"
        @update:model-value="chooseKey(String($event))"
      />
      <AppSelect
        v-model="foreign.match"
        :options="matches"
        label="Match"
      />
    </div>
    <div
      class="inspector__relationship"
      data-testid="foreign-relationship"
    >
      <div class="inspector__relation">
        <strong>{{ design.draft.name || "New table" }} · new</strong>
        <span>{{
          foreign.columnIds
            .map(
              (id) =>
                design.draft.columns.find((column) => column.id === id)?.name || "Choose column"
            )
            .join(" + ") || "Choose columns"
        }}</span>
      </div>
      <span class="inspector__arrow">N → 1</span>
      <div class="inspector__relation">
        <strong>{{ schemaChoices.find((choice) => choice.value === schemaId)?.label
        }}{{ foreign.targetLabel ? "." + foreign.targetLabel : " · target" }}</strong>
        <span>{{ foreign.targetColumns.join(" + ") || "Choose key" }}</span>
      </div>
    </div>
    <h3>Column mapping</h3>
    <div
      v-for="(target, at) in foreign.targetColumns"
      :key="target"
      class="inspector__mapping"
    >
      <AppSelect
        :model-value="foreign.columnIds[at] ?? ''"
        :options="design.columnChoices.value"
        label="Local column"
        :data-testid="`foreign-column-${at}`"
        @update:model-value="foreign.columnIds[at] = String($event)"
      />
      <span class="inspector__arrow">→</span>
      <AppInput
        :model-value="target"
        label="Target column"
        readonly
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
      A foreign key names as many columns as it points at: {{ arity }}
      {{ arity === 1 ? "column" : "columns" }} are expected here.
    </AppBanner>
    <div class="inspector__row">
      <AppSelect
        v-model="foreign.onDelete"
        :options="actions"
        label="On delete"
        data-testid="foreign-on-delete"
      />
      <AppSelect
        v-model="foreign.onUpdate"
        :options="actions"
        label="On update"
      />
      <AppCheckbox
        v-model="foreign.deferrable"
        label="Deferrable"
        dense
      />
      <AppCheckbox
        v-model="foreign.initiallyDeferred"
        label="Initially deferred"
        dense
        :disable="!foreign.deferrable"
      />
    </div>
  </div>
  <p
    v-else
    class="inspector__note"
  >
    No foreign keys.
  </p>
</template>

<style scoped>
.inspector {
  display: grid;
  gap: 12px;
}
.inspector h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--dp-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.inspector__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}
.inspector__relationship {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 32px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}
.inspector__relation {
  border: 1px solid var(--dp-border);
  border-radius: 4px;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.inspector__relation strong {
  display: block;
  background: var(--dp-chrome-raised);
  border-bottom: 1px solid var(--dp-border);
  padding: 6px 8px;
}
.inspector__relation > span {
  display: block;
  padding: 5px 8px;
  color: var(--dp-link);
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
}
.inspector__arrow {
  text-align: center;
  color: var(--dp-link);
}
.inspector__mapping {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 25px minmax(0, 1fr);
  gap: 5px;
  align-items: center;
}
.inspector__note {
  color: var(--dp-text-muted);
}
@container table-designer (max-width: 560px) {
  .inspector__row,
  .inspector__relationship {
    grid-template-columns: minmax(0, 1fr);
  }
  .inspector__relationship > .inspector__arrow {
    transform: rotate(90deg);
  }
}
</style>
