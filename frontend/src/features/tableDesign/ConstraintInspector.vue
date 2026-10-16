<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { t } from "@/shared/i18n"
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
      <h3 class="dp-overline">
        {{ t('table_design.primary_key') }}
      </h3>
      <div class="constraints__badges">
        <AppCheckbox
          v-for="column in draft.columns"
          :key="column.id"
          :model-value="draft.primaryKey.includes(column.id)"
          :label="column.name || t('table_design.unnamed')"
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
        <h3 class="dp-overline">
          {{ t('table_design.constraints.unique_constraint') }}
        </h3>
        <AppIconButton
          :icon="appIcons.deleteOutline"
          :tooltip="unique.name ? t('table_design.constraints.remove_named', { name: unique.name }) : t('table_design.constraints.remove_unique')"
          @click="emit('remove', unique.id)"
        />
      </div>
      <div class="constraints__fields">
        <AppInput
          v-model="unique.name"
          :label="t('table_design.name')"
          :placeholder="t('table_design.automatic_name')"
        />
        <AppCheckbox
          v-model="unique.nullsNotDistinct"
          :label="t('table_design.constraints.nulls_not_distinct')"
          dense
          :disable="!nullsMayRepeat"
        />
      </div>
      <div class="constraints__badges">
        <AppCheckbox
          v-for="column in draft.columns"
          :key="column.id"
          :model-value="unique.columnIds.includes(column.id)"
          :label="column.name || t('table_design.unnamed')"
          dense
          @update:model-value="membership(unique.columnIds, column.id, $event)"
        />
      </div>
      <details class="constraints__advanced dp-disclosure">
        <summary>{{ t('table_design.constraints.deferrability') }}</summary>
        <AppCheckbox
          v-model="unique.deferrable"
          :label="t('table_design.deferrable')"
          dense
        />
        <AppCheckbox
          v-model="unique.initiallyDeferred"
          :label="t('table_design.initially_deferred')"
          dense
          :disable="!unique.deferrable"
        />
      </details>
    </section>
    <AppButton
      variant="quiet"
      :icon="appIcons.add"
      :label="t('table_design.constraints.unique_constraint')"
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
        <h3 class="dp-overline">
          {{ t('table_design.constraints.check') }}
        </h3>
        <AppIconButton
          :icon="appIcons.deleteOutline"
          :tooltip="check.name ? t('table_design.constraints.remove_named', { name: check.name }) : t('table_design.constraints.remove_check')"
          @click="emit('remove', check.id)"
        />
      </div>
      <div class="constraints__fields">
        <AppInput
          v-model="check.name"
          :label="t('table_design.name')"
          :placeholder="t('table_design.automatic_name')"
        />
        <PredicateField
          :design-id="designId"
          owner="check"
          :owner-id="check.id"
          testid="check-predicate"
          :label="t('table_design.expression')"
        />
      </div>
    </section>
    <details class="constraints__advanced dp-disclosure">
      <summary>{{ t('table_design.constraints.key_order') }}</summary>
      <AppSelect
        v-model="draft.primaryKey"
        :options="design.columnChoices.value"
        :label="t('table_design.columns')"
        multiple
      />
    </details>
  </div>
</template>

<style scoped>
.constraints {
  display: grid;
  gap: var(--dp-space-3);
}
.constraints h3 {
  margin: 0 0 var(--dp-space-2);
}
.constraints__heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--dp-space-2);
}
.constraints__heading h3 {
  margin: 0;
}
.constraints__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-3);
  align-items: end;
  margin: var(--dp-space-3) 0;
}
.constraints__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
}
.constraints__badges > * {
  border: 1px solid var(--dp-border);
  padding: var(--dp-space-half) var(--dp-space-2);
  border-radius: var(--dp-radius-control);
}
.constraints__rule {
  border-top: 1px solid var(--dp-border);
  padding-top: var(--dp-space-2);
}
.constraints__advanced {
  margin-top: var(--dp-space-3);
  color: var(--dp-text-muted);
}
.constraints__advanced summary {
  cursor: pointer;
}
.constraints__expression {
  margin-top: var(--dp-space-3);
}
@container table-designer (max-width: 560px) {
  .constraints__fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
