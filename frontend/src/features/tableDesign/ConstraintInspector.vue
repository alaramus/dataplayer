<script setup lang="ts">
import { computed } from "vue"

import { AppButton, AppCheckbox, AppIconButton, AppInput, AppSelect } from "@/shared/ui"

import { useDesign } from "./design"
import { newUnique } from "./draft"
import PredicateField from "./PredicateField.vue"

const props = defineProps<{ designId: string }>()
const emit = defineEmits<{ remove: [id: string] }>()
const design = useDesign(props.designId)
const { draft } = design
const nullsMayRepeat = computed(() => design.options.value?.nulls_not_distinct_supported === true)

function membership(ids: string[], id: string, checked: boolean): void {
  const at = ids.indexOf(id)
  if (checked && at < 0) ids.push(id)
  if (!checked && at >= 0) ids.splice(at, 1)
}
function addUnique(): void {
  draft.uniques.push(newUnique(draft.columns[0]?.id ?? ""))
}
</script>

<template>
  <div
    class="constraints"
    data-testid="constraints-inspector"
  >
    <section>
      <h3>Primary key</h3>
      <div class="constraints__badges">
        <AppCheckbox
          v-for="column in draft.columns"
          :key="column.id"
          :model-value="draft.primaryKey.includes(column.id)"
          :label="column.name || '(unnamed)'"
          dense
          @update:model-value="membership(draft.primaryKey, column.id, $event)"
        />
      </div>
    </section>
    <section
      v-for="unique in draft.uniques"
      :key="unique.id"
      class="constraints__rule"
      data-testid="unique-inspector"
    >
      <div class="constraints__heading">
        <h3>Unique constraint</h3>
        <AppIconButton
          icon="delete_outline"
          :tooltip="`Remove ${unique.name || 'unique constraint'}`"
          @click="emit('remove', unique.id)"
        />
      </div>
      <div class="constraints__fields">
        <AppInput
          v-model="unique.name"
          label="Name"
          placeholder="Automatic name"
        />
        <AppCheckbox
          v-model="unique.nullsNotDistinct"
          label="Nulls not distinct"
          dense
          :disable="!nullsMayRepeat"
        />
      </div>
      <div class="constraints__badges">
        <AppCheckbox
          v-for="column in draft.columns"
          :key="column.id"
          :model-value="unique.columnIds.includes(column.id)"
          :label="column.name || '(unnamed)'"
          dense
          @update:model-value="membership(unique.columnIds, column.id, $event)"
        />
      </div>
      <details class="constraints__advanced">
        <summary>Deferrability</summary>
        <AppCheckbox
          v-model="unique.deferrable"
          label="Deferrable"
          dense
        />
        <AppCheckbox
          v-model="unique.initiallyDeferred"
          label="Initially deferred"
          dense
          :disable="!unique.deferrable"
        />
      </details>
    </section>
    <AppButton
      variant="quiet"
      icon="add"
      label="Unique constraint"
      data-testid="add-unique"
      @click="addUnique"
    />
    <section
      v-for="check in draft.checks"
      :key="check.id"
      class="constraints__rule"
      data-testid="check-inspector"
    >
      <div class="constraints__heading">
        <h3>CHECK</h3>
        <AppIconButton
          icon="delete_outline"
          :tooltip="`Remove ${check.name || 'check'}`"
          @click="emit('remove', check.id)"
        />
      </div>
      <div class="constraints__fields">
        <AppInput
          v-model="check.name"
          label="Name"
          placeholder="Automatic name"
        />
        <PredicateField
          :design-id="designId"
          owner="check"
          :owner-id="check.id"
          testid="check-predicate"
          label="Expression"
        />
      </div>
    </section>
    <details class="constraints__advanced">
      <summary>Primary key · column order</summary>
      <AppSelect
        v-model="draft.primaryKey"
        :options="design.columnChoices.value"
        label="Columns"
        multiple
      />
    </details>
  </div>
</template>

<style scoped>
.constraints {
  display: grid;
  gap: 12px;
}
.constraints h3 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--dp-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.constraints__heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.constraints__heading h3 {
  margin: 0;
}
.constraints__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: end;
  margin: 12px 0;
}
.constraints__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.constraints__badges > * {
  border: 1px solid var(--dp-border);
  padding: 3px 8px;
  border-radius: 4px;
}
.constraints__rule {
  border-top: 1px solid var(--dp-border);
  padding-top: 10px;
}
.constraints__advanced {
  margin-top: 12px;
  color: var(--dp-text-muted);
}
.constraints__advanced summary {
  cursor: pointer;
}
.constraints__expression {
  margin-top: 12px;
}
@container table-designer (max-width: 560px) {
  .constraints__fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
