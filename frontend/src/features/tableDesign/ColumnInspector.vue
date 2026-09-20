<script setup lang="ts">
import { computed } from "vue"

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
    { label: "None", value: "none" },
    { label: "Default value", value: "literal" },
    { label: "Default function", value: "expression" },
    { label: "Generated · stored", value: "generated" },
  ]
  // Only where the server says the type can carry one: PostgreSQL means
  // integers, and offering it on text would be offering a refusal.
  if (type.value?.identity_supported === true) {
    choices.splice(3, 0, { label: "Identity", value: "identity" })
  }
  return choices
})

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
        label="Name"
        data-testid="column-name"
      />
      <AppSelect
        v-model="column.typeCode"
        :options="design.typeChoices.value"
        label="Data type"
        data-testid="column-type"
      />
    </div>

    <div class="inspector__row">
      <AppSelect
        :model-value="column.generation.kind"
        :options="generationChoices"
        label="Value generation"
        data-testid="column-generation"
        @update:model-value="changeGeneration(String($event))"
      />
      <AppInput
        v-if="column.generation.kind === 'literal' || column.generation.kind === 'none'"
        :model-value="column.generation.kind === 'literal' ? column.generation.value : ''"
        label="Default value"
        data-testid="column-default"
        @update:model-value="changeDefault"
      />
      <AppSelect
        v-else-if="column.generation.kind === 'expression'"
        v-model="column.generation.function"
        :options="defaultFunctions"
        label="Function"
        data-testid="column-default-function"
      />
      <template v-else-if="column.generation.kind === 'identity'">
        <AppSelect
          v-model="column.generation.generated"
          :options="[
            { label: 'Always', value: 'always' },
            { label: 'Unless a value is given', value: 'by_default' },
          ]"
          label="Numbered"
        />
        <AppNumberInput
          v-model="column.generation.start"
          label="Starting at"
          placeholder="1"
        />
        <AppNumberInput
          v-model="column.generation.increment"
          label="Step"
          placeholder="1"
        />
      </template>
      <template v-else-if="column.generation.kind === 'generated'">
        <AppSelect
          v-model="column.generation.function"
          :options="computedFunctions"
          label="Function"
        />
        <AppSelect
          v-model="column.generation.columnId"
          :options="otherColumns"
          label="Of column"
        />
      </template>
    </div>

    <div class="inspector__row">
      <AppCheckbox
        v-model="column.notNull"
        label="Not null"
        dense
        data-testid="column-not-null"
      />
      <AppCheckbox
        :model-value="inKey"
        label="Primary key"
        dense
        data-testid="column-in-key"
        @update:model-value="changeKeyMembership"
      />
    </div>
    <AppBanner
      v-if="inKey && !column.notNull && column.generation.kind !== 'identity'"
      tone="warning"
    >
      A column of the primary key must have a value.
    </AppBanner>
    <div class="inspector__row">
      <AppSelect
        v-model="column.collation"
        :options="collations"
        label="Collation"
      />
      <AppInput
        v-model="column.comment"
        label="Comment"
      />
    </div>
    <details
      v-if="takes.length || type?.array_supported"
      class="inspector__advanced"
    >
      <summary>Type parameters &amp; array</summary>
      <div class="inspector__row">
        <AppNumberInput
          v-if="takes.includes('length')"
          v-model="column.length"
          label="Length"
          data-testid="column-length"
        />
        <AppNumberInput
          v-if="takes.includes('precision')"
          v-model="column.precision"
          label="Precision"
        />
        <AppNumberInput
          v-if="takes.includes('scale')"
          v-model="column.scale"
          label="Scale"
        />
        <AppCheckbox
          v-if="type?.array_supported"
          :model-value="column.dimensions > 0"
          label="Array"
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
  align-items: start;
}
.inspector__row > * {
  min-width: 0;
}
.inspector__advanced {
  border-top: 1px solid var(--dp-border);
  padding-top: var(--dp-space-2);
}
.inspector__advanced summary {
  cursor: pointer;
  color: var(--dp-text-muted);
  margin-bottom: var(--dp-space-2);
}
@container table-designer (max-width: 560px) {
  .inspector__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
